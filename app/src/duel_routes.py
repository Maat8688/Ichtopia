"""Routes en socket-handlers voor de 1-tegen-1 duels.

Hier zit alles wat met de database te maken heeft: het opslaan van de uitslag,
het verrekenen van elo en het bijschrijven van XP. De spelregels zelf staan in
duel.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import current_user, login_required
from flask_socketio import SocketIO, emit, join_room

from . import app
from .duel import (DEFAULT_QUESTIONS, DEFAULT_SECONDS, Duel, DuelManager, DuelPlayer)
from .kahoot import MAP_CATEGORIES, MAP_FILES, MAP_NIVEAUS
from .models import DuelMatch, User, db
from .progress import XP_DAILY_CAP, duelXp, newRating
from .sockets import registerDisconnect

duel = Blueprint('duel', __name__)
duelManager = DuelManager()

REVEAL_SECONDS = 4
START_COUNTDOWN = 3

# Elo is nul-som: om de beurt winnen levert niemand iets op, dus dat hoeft ook
# niet geremd te worden. Wat wel werkt is eenzijdig voeren - iemand die zich
# steeds expres laat verliezen, of een tweede account dat alleen bestaat om
# punten weg te geven. Daarom tellen alleen de eerste paar overwinningen op
# dezelfde tegenstander per dag. Twee rivalen die de hele middag tegen elkaar
# spelen en netjes wisselen, merken hier niets van.
RATED_WINS_PER_PAIR_PER_DAY = 3


def duelRoom(code: str) -> str:
    return f'duel-{code}'


def playerFromUser(user) -> DuelPlayer:
    return DuelPlayer(userId=user.id, name=user.username,
                      rating=user.rating, level=user.level)


# ----------------------------------------------------------------------
# HTTP routes
# ----------------------------------------------------------------------
@duel.route('/duel')
@login_required
def lobby():
    running = duelManager.duelForUser(current_user.id)
    return render_template(
        'duel_lobby.html',
        openDuels=duelManager.openDuels(exceptUserId=current_user.id),
        running=running,
        maps=list(MAP_FILES.keys()),
        categories=MAP_CATEGORIES,
        niveaus=MAP_NIVEAUS,
        defaultQuestions=DEFAULT_QUESTIONS,
        defaultSeconds=DEFAULT_SECONDS,
    )


@duel.route('/duel/nieuw', methods=['POST'])
@login_required
def create():
    try:
        newDuel = duelManager.createDuel(
            creator=playerFromUser(current_user),
            mapName=request.form.get('KaartInput', ''),
            mode=request.form.get('mode', 'MultipleChoise'),
            categories=request.form.getlist('questions'),
            questionCount=request.form.get('questionCount', DEFAULT_QUESTIONS),
            seconds=request.form.get('seconds', DEFAULT_SECONDS),
            niveau=request.form.get('niveau') or None,
            open_=request.form.get('open') != '0',
        )
    except (ValueError, TypeError) as e:
        return render_template('duel_lobby.html',
                               error=str(e) or 'Er ging iets mis.',
                               openDuels=duelManager.openDuels(exceptUserId=current_user.id),
                               running=None, maps=list(MAP_FILES.keys()),
                               categories=MAP_CATEGORIES, niveaus=MAP_NIVEAUS,
                               defaultQuestions=DEFAULT_QUESTIONS,
                               defaultSeconds=DEFAULT_SECONDS)
    return redirect(url_for('duel.play', code=newDuel.code))


@duel.route('/duel/<code>')
@login_required
def play(code):
    currentDuel = duelManager.getDuel(code)
    if currentDuel is None:
        return render_template('duel_lobby.html',
                               error='Dit duel bestaat niet (meer).',
                               openDuels=duelManager.openDuels(exceptUserId=current_user.id),
                               running=None, maps=list(MAP_FILES.keys()),
                               categories=MAP_CATEGORIES, niveaus=MAP_NIVEAUS,
                               defaultQuestions=DEFAULT_QUESTIONS,
                               defaultSeconds=DEFAULT_SECONDS), 404
    mine = currentDuel.playerFor(current_user.id) is not None
    if not mine and (currentDuel.isFull or currentDuel.state != 'lobby'):
        return render_template('duel_lobby.html',
                               error='Dit duel zit al vol.',
                               openDuels=duelManager.openDuels(exceptUserId=current_user.id),
                               running=None, maps=list(MAP_FILES.keys()),
                               categories=MAP_CATEGORIES, niveaus=MAP_NIVEAUS,
                               defaultQuestions=DEFAULT_QUESTIONS,
                               defaultSeconds=DEFAULT_SECONDS), 403
    return render_template('duel_play.html', duel=currentDuel, map=currentDuel.map)


# ----------------------------------------------------------------------
# Uitslag verwerken
# ----------------------------------------------------------------------
def winsTodayAgainst(winnerId: int, loserId: int) -> int:
    """Hoe vaak deze speler vandaag al van deze tegenstander won, in duels die telden."""
    since = datetime.now(timezone.utc) - timedelta(days=1)
    return DuelMatch.query.filter(
        DuelMatch.played_at >= since,
        DuelMatch.rated.is_(True),
        db.or_(
            db.and_(DuelMatch.one_id == winnerId, DuelMatch.two_id == loserId,
                    DuelMatch.one_score > DuelMatch.two_score),
            db.and_(DuelMatch.two_id == winnerId, DuelMatch.one_id == loserId,
                    DuelMatch.two_score > DuelMatch.one_score),
        ),
    ).count()


def isRated(userOne, userTwo, resultOne: float) -> bool:
    """Telt dit duel voor de elo?

    Gelijkspel altijd: daar valt niets mee te voeren. Bij winst kijken we hoe
    vaak de winnaar vandaag al van deze tegenstander won.
    """
    if resultOne == 0.5:
        return True
    winner, loser = ((userOne, userTwo) if resultOne == 1.0 else (userTwo, userOne))
    return winsTodayAgainst(winner.id, loser.id) < RATED_WINS_PER_PAIR_PER_DAY


def applyResults(finishedDuel: Duel) -> dict[int, dict]:
    """Verreken elo en XP en sla het duel op. Geeft per speler wat er veranderde."""
    with finishedDuel.lock:
        if finishedDuel.ratingApplied or len(finishedDuel.players) < 2:
            return {}
        finishedDuel.ratingApplied = True

    one, two = finishedDuel.players
    changes: dict[int, dict] = {}

    with app.app_context():
        userOne = db.session.get(User, one.userId)
        userTwo = db.session.get(User, two.userId)
        if userOne is None or userTwo is None:
            return {}

        beforeOne, beforeTwo = userOne.rating, userTwo.rating

        if one.score > two.score:
            resultOne = 1.0
        elif one.score < two.score:
            resultOne = 0.0
        else:
            resultOne = 0.5

        rated = isRated(userOne, userTwo, resultOne)

        if rated:
            afterOne = newRating(beforeOne, beforeTwo, resultOne, userOne.duelsPlayed)
            afterTwo = newRating(beforeTwo, beforeOne, 1 - resultOne, userTwo.duelsPlayed)
            userOne.rating, userTwo.rating = afterOne, afterTwo
            if resultOne == 1.0:
                userOne.duels_won += 1
                userTwo.duels_lost += 1
            elif resultOne == 0.0:
                userOne.duels_lost += 1
                userTwo.duels_won += 1
            else:
                userOne.duels_drawn += 1
                userTwo.duels_drawn += 1
        else:
            afterOne, afterTwo = beforeOne, beforeTwo

        xpOne = userOne.addXp(duelXp(resultOne == 1.0, one.score), cap=XP_DAILY_CAP)
        xpTwo = userTwo.addXp(duelXp(resultOne == 0.0, two.score), cap=XP_DAILY_CAP)

        match = DuelMatch(
            map_name=finishedDuel.mapName,
            questions=len(finishedDuel.questions),
            rated=rated,
            one_id=userOne.id, two_id=userTwo.id,
            one_score=one.score, two_score=two.score,
            one_rating_before=beforeOne, two_rating_before=beforeTwo,
            one_rating_after=afterOne, two_rating_after=afterTwo,
        )
        db.session.add(match)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception('Duel opslaan mislukt')
            return {}

        changes[one.userId] = {
            'rated': rated, 'ratingBefore': beforeOne, 'rating': afterOne,
            'ratingChange': afterOne - beforeOne, 'xpEarned': xpOne,
            'level': userOne.level, 'levelProgress': userOne.levelProgress,
        }
        changes[two.userId] = {
            'rated': rated, 'ratingBefore': beforeTwo, 'rating': afterTwo,
            'ratingChange': afterTwo - beforeTwo, 'xpEarned': xpTwo,
            'level': userTwo.level, 'levelProgress': userTwo.levelProgress,
        }

    # Zodat een herverbinding na afloop nog de juiste cijfers ziet.
    finishedDuel.resultChanges = changes
    return changes


# ----------------------------------------------------------------------
# Sockets
# ----------------------------------------------------------------------
def setupDuelSockets(socketio: SocketIO):

    def sendState(currentDuel: Duel):
        for player in currentDuel.players:
            if player.sid:
                changes = currentDuel.resultChanges.get(player.userId)
                socketio.emit('duelState', currentDuel.stateFor(player, changes), to=player.sid)

    def sendFinished(currentDuel: Duel):
        currentDuel.finish()
        changes = applyResults(currentDuel)
        for player in currentDuel.players:
            if player.sid:
                socketio.emit('duelFinished',
                              currentDuel.finishedPayload(player, changes.get(player.userId)),
                              to=player.sid)

    def sendReveal(currentDuel: Duel):
        reveal = currentDuel.reveal()
        if reveal is None:
            return
        for player in currentDuel.players:
            if player.sid:
                socketio.emit('duelReveal', currentDuel.resultFor(player), to=player.sid)
        socketio.start_background_task(afterReveal, currentDuel, currentDuel.questionRun)

    def afterReveal(currentDuel: Duel, run: int):
        socketio.sleep(REVEAL_SECONDS)
        if currentDuel.state == 'reveal' and currentDuel.questionRun == run:
            startNextQuestion(currentDuel)

    def questionTimer(currentDuel: Duel, run: int):
        socketio.sleep(currentDuel.seconds + 0.5)
        if currentDuel.state == 'question' and currentDuel.questionRun == run:
            sendReveal(currentDuel)

    def startNextQuestion(currentDuel: Duel):
        if currentDuel.nextQuestion():
            socketio.emit('duelQuestion', currentDuel.questionPayload(), to=duelRoom(currentDuel.code))
            socketio.start_background_task(questionTimer, currentDuel, currentDuel.questionRun)
        else:
            sendFinished(currentDuel)

    def startDuel(currentDuel: Duel, run: int):
        socketio.sleep(START_COUNTDOWN)
        if currentDuel.state == 'lobby' and currentDuel.questionRun == run:
            startNextQuestion(currentDuel)

    @socketio.on('duelJoin')
    def onJoin(data):  # verwacht {'code': str}
        if not current_user.is_authenticated:
            emit('duelError', {'message': 'Log in om te duelleren.', 'fatal': True})
            return
        currentDuel = duelManager.getDuel((data or {}).get('code'))
        if currentDuel is None:
            emit('duelError', {'message': 'Dit duel bestaat niet (meer).', 'fatal': True})
            return
        try:
            player = currentDuel.join(playerFromUser(current_user))
        except ValueError as e:
            emit('duelError', {'message': str(e), 'fatal': True})
            return

        player.sid = request.sid
        player.connected = True
        join_room(duelRoom(currentDuel.code))
        sendState(currentDuel)

        if (currentDuel.state == 'lobby' and currentDuel.isFull
                and all(p.connected for p in currentDuel.players)):
            socketio.emit('duelStarting', {'seconds': START_COUNTDOWN},
                          to=duelRoom(currentDuel.code))
            socketio.start_background_task(startDuel, currentDuel, currentDuel.questionRun)

    @socketio.on('duelAnswer')
    def onAnswer(data):  # verwacht {'code': str, 'answer': str, 'hashed': bool}
        if not current_user.is_authenticated:
            return
        data = data or {}
        currentDuel = duelManager.getDuel(data.get('code'))
        if currentDuel is None:
            return
        accepted, bothAnswered = currentDuel.answer(current_user.id, data.get('answer', ''),
                                                    bool(data.get('hashed')))
        if not accepted:
            emit('duelAnswerRejected', {})
            return
        player = currentDuel.playerFor(current_user.id)
        opponent = currentDuel.opponentOf(player) if player else None
        if opponent and opponent.sid:
            socketio.emit('duelOpponentAnswered', {}, to=opponent.sid)
        if bothAnswered:
            sendReveal(currentDuel)

    @registerDisconnect
    def onDisconnect(sid):
        for currentDuel in list(duelManager.duels.values()):
            player = currentDuel.playerBySid(sid)
            if player is None:
                continue
            player.connected = False
            player.sid = None
            opponent = currentDuel.opponentOf(player)
            if opponent and opponent.sid:
                socketio.emit('duelOpponentLeft', {'name': player.name}, to=opponent.sid)
