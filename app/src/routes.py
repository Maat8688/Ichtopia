import functools
from flask import Blueprint, abort, render_template, request, redirect, url_for
from flask_socketio import SocketIO, send, emit
from flask_login import current_user
from . import app, sessionManager
from .map import mapSession, SessionGamemode, SessionManager
from .kahoot import MAP_FILES
from .models import User, db
from .progress import XP_DAILY_CAP, practiceXp
from .security import AttemptLimiter, clientIp
from .gebruik import legKlaar, legSessie

main = Blueprint('main', __name__)

# Rem op het aanmaken van oefensessies. Een hele klas zit vaak achter een IP
# (het schoolnetwerk), dus ruim genoeg voor dertig leerlingen die een paar keer
# opnieuw beginnen, maar een script kan niet in een keer alle plekken vullen.
practiceLimiter = AttemptLimiter(maxAttempts=200, window=10 * 60)


@main.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        kaart = request.form.get('KaartInput')
        if kaart not in MAP_FILES:
            return redirect(url_for('main.index'))
        ip = clientIp()
        if practiceLimiter.blocked(ip):
            abort(429)
        practiceLimiter.registerFailure(ip)
        niveau = request.form.get('niveau') or None
        newSession = mapSession.fromSVG(MAP_FILES[kaart], request.form.get('mode'),
                                        request.form.getlist('questions'), niveau)
        if not newSession.questions:
            return redirect(url_for('main.index'))
        newSession.niveau = niveau
        newSession.kaartTotaal = kaartTotaal(kaart, niveau)
        if request.form.get('soort') == 'toets':
            aantal = request.form.get('toetsVragen', '20')
            newSession.startToets(None if aantal == 'alle' else _getal(aantal, 20))
        id = sessionManager.createSession(newSession)
        legSessie('oefenen_start', newSession)
        return redirect(url_for('main.learn', sessionToken=id))
    return render_template('index.html', **homeNotes())

@functools.lru_cache(maxsize=None)
def kaartTotaal(kaart: str, niveau: str | None) -> int:
    """Hoeveel vragen de hele kaart heeft (alle onderdelen) op dit niveau."""
    from .kahoot import MAP_CATEGORIES
    return len(mapSession.fromSVG(MAP_FILES[kaart], 'MultipleChoise',
                                  list(MAP_CATEGORIES[kaart]), niveau).questions)


def _getal(tekst, standaard: int) -> int:
    try:
        return max(1, min(int(tekst), 500))
    except (TypeError, ValueError):
        return standaard


def homeNotes() -> dict:
    """Wat er op de kladblaadjes van de startpagina staat: een duel dat op een
    tegenstander wacht, en de top drie van de elo-ranglijst."""
    # Hier geimporteerd: duel_routes en ranking laden na dit bestand.
    from .duel_routes import duelManager
    from .ranking import eloBoard, ownEloRank

    me = current_user if current_user.is_authenticated else None
    openDuels = duelManager.openDuels(exceptUserId=me.id if me else None)
    top = eloBoard(limit=3)
    myRank = ownEloRank(me) if me else 0
    return {
        'openDuel': openDuels[0] if openDuels else None,
        'openDuelCount': len(openDuels),
        'topElo': top,
        'myEloRank': myRank,
        'meInTop': any(row['id'] == me.id for row in top) if me else False,
    }

@main.route('/privacy')
def privacy():
    return render_template('privacy.html')


@main.route('/learn')
def learn():
    session = sessionManager.findSession(request.args.get('sessionToken'))
    if session is not None:
        return render_template('learn.html', map=session)
    else:
        return redirect(url_for('main.index'))
    

def awardPracticeXp(session: mapSession) -> dict | None:
    """Schrijf XP bij voor een afgeronde oefensessie.

    Alleen voor wie ingelogd is; zonder account valt er niets bij te schrijven.
    De rem per dag zit in User.addXp, zodat dezelfde kleine kaart eindeloos
    herhalen niets meer oplevert.
    """
    if not current_user.is_authenticated:
        return None
    amount = practiceXp(len(session.questions), session.totalGuesses)
    with app.app_context():
        user = db.session.get(User, current_user.id)
        if user is None:
            return None
        earned = user.addXp(amount, cap=XP_DAILY_CAP)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception('XP bijschrijven mislukt')
            return None
        return {
            'earned': earned,
            'capped': earned < amount,
            'xp': user.xp,
            'level': user.level,
            'levelProgress': user.levelProgress,
        }


def setupSockets(socketio: SocketIO):
    def sessionFrom(data) -> mapSession | None:
        """De sessie bij dit token, of None als hij is opgeruimd.

        Sessies worden na een tijd stilte weggegooid, anders loopt het geheugen
        van de server vol. Wie daarna nog een antwoord instuurt, krijgt een
        melding in plaats van een pagina die niets meer doet.
        """
        if not isinstance(data, dict):
            return None
        session = sessionManager.findSession(data.get('sessionToken'))
        if session is None:
            emit('sessionExpired')
            return None
        session.touch()
        return session

    def stuurVraag(session):
        if session.sessionMode == 1:
            emit('question', {'question': session.hash(session.currentQuestion.id), 'mcAwnsers': session.mcAwnsers})
        elif session.sessionMode == 2:
            emit('question', {'question': session.hash(session.currentQuestion.id)})
        elif session.sessionMode == 3:
            emit('question', {'question': session.currentQuestion.displayName})

    def toetsKlaar(session):
        """Uitslag van de toets; pas nu mag de kaart laten zien wat goed was."""
        uitslag = session.toetsUitslag()
        emit('setMapState', session.getMapState())
        if not getattr(session, 'geteld', False):
            session.geteld = True
            legKlaar(session, session.getFinishedData(), cijfer=uitslag['cijfer'])
            uitslag['xp'] = awardPracticeXp(session)
        emit('toetsKlaar', uitslag)

    def toetsAntwoord(session, data):
        # Een antwoord dat binnenkomt na de laatste vraag (dubbelklik) telt niet.
        if session.finished:
            toetsKlaar(session)
            return
        session.beantwoordToets(data.get('awnser', ''), bool(data.get('hashed')))
        if session.volgendeToetsvraag():
            emit('toetsVoortgang', session.toetsVoortgang())
            toetsKlaar(session)
            return
        emit('toetsVoortgang', session.toetsVoortgang())
        stuurVraag(session)

    @socketio.on('answerQuestion')
    def answerQuestion(data): # expects {'awnser': str, 'hashed': bool, 'sessionToken': str}
        session = sessionFrom(data)
        if session is None:
            return
        if session.toets:
            toetsAntwoord(session, data)
            return
        if session.currentQuestion is None:
            return

        if session.awnserQuestion(data.get('awnser', ''), bool(data.get('hashed'))):
            emit('questionCorrect')
            # emit('updateMap', {'questionId': questionId, 'status': 'correct'})
            emit('setMapState', session.getMapState())
        else:
            emit('questionIncorrect')
            # emit('updateMap', {'questionId': questionId, 'status': 'incorrect'})
            emit('setMapState', session.getMapState())

        emit('setProgressBar', session.getProgresBar())

        if session.nextQuestion():
            # emit('finished', {'score': currentSession.score, 'totalGuesses': currentSession.totalGuesses})
            send(f"Finished with a score of {session.score}/{session.totalGuesses}")
            uitslag = session.getFinishedData()
            xp = None
            # Een keer tellen, ook als er daarna nog een antwoord binnenkomt.
            if not getattr(session, 'geteld', False):
                session.geteld = True
                legKlaar(session, uitslag)
                xp = awardPracticeXp(session)
            emit('finished', {"Overvieuw": uitslag, "xp": xp})
            return

        if session.sessionMode == 1:
            emit('question', {'question': session.hash(session.currentQuestion.id), 'mcAwnsers': session.mcAwnsers})
        elif session.sessionMode == 2:
            emit('question', {'question': session.hash(session.currentQuestion.id)})
        elif session.sessionMode == 3:
            emit('question', {'question': session.currentQuestion.displayName})

    @socketio.on('getQuestion')
    def getQuestion(data): # expects {'sessionToken': str}
        session = sessionFrom(data)
        if session is None:
            return
        if session.toets:
            emit('toetsVoortgang', session.toetsVoortgang())
            if session.finished:
                toetsKlaar(session)
            else:
                stuurVraag(session)
            return
        if session.currentQuestion is None:
            return
        if session.sessionMode == 1:
            emit('question', {'question': session.hash(session.currentQuestion.id), 'mcAwnsers': session.mcAwnsers})
        elif session.sessionMode == 2:
            emit('question', {'question': session.hash(session.currentQuestion.id)})
        elif session.sessionMode == 3:
            emit('question', {'question': session.currentQuestion.displayName})

    @socketio.on('getProgressbar')
    def getProgressbar(data):
        session = sessionFrom(data)
        if session is None:
            return
        if session.toets:
            emit('toetsVoortgang', session.toetsVoortgang())
            return
        emit('setProgressBar', session.getProgresBar())