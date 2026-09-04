"""Routes en socket-handlers voor de klassikale quiz (Kahoot-modus)."""
from __future__ import annotations

import sys

from flask import Blueprint, render_template, request, redirect, url_for, session, abort
from flask_socketio import SocketIO, emit, join_room

from .kahoot import (
    KahootManager, KahootGame, MAP_CATEGORIES, MAP_FILES,
    MODE_MULTIPLECHOICE, MODE_CLICKTHECOUNTRY,
)

kahoot = Blueprint('kahoot', __name__)
kahootManager = KahootManager()

HOST_SESSION_KEY = 'kahootHostTokens'


def hostRoom(pin: str) -> str:
    return f'kahoot-host-{pin}'


def playerRoom(pin: str) -> str:
    return f'kahoot-players-{pin}'


def rememberHost(game: KahootGame):
    tokens = session.get(HOST_SESSION_KEY, {})
    tokens[game.pin] = game.hostToken
    # Alleen de laatste paar bewaren, anders groeit de cookie.
    session[HOST_SESSION_KEY] = dict(list(tokens.items())[-5:])


def isHost(game: KahootGame) -> bool:
    tokens = session.get(HOST_SESSION_KEY, {})
    return tokens.get(game.pin) == game.hostToken


# ----------------------------------------------------------------------
# HTTP routes
# ----------------------------------------------------------------------
@kahoot.route('/host', methods=['GET', 'POST'])
def host():
    error = None
    if request.method == 'POST':
        try:
            game = kahootManager.createGame(
                mapName=request.form.get('KaartInput', ''),
                mode=request.form.get('mode', 'MultipleChoise'),
                categories=request.form.getlist('questions'),
                questionCount=request.form.get('questionCount', 10),
                secondsPerQuestion=request.form.get('seconds', 20),
            )
        except (ValueError, TypeError) as e:
            error = str(e) or 'Er ging iets mis bij het aanmaken van de quiz.'
        else:
            rememberHost(game)
            return redirect(url_for('kahoot.hostGame', pin=game.pin))
    return render_template('kahoot_setup.html', categories=MAP_CATEGORIES,
                           maps=list(MAP_FILES.keys()), error=error)


@kahoot.route('/host/<pin>')
def hostGame(pin):
    game = kahootManager.getGame(pin)
    if game is None or not isHost(game):
        return redirect(url_for('kahoot.host'))
    joinUrl = url_for('kahoot.join', _external=True)
    return render_template('kahoot_host.html', game=game, map=game.map,
                           hostToken=game.hostToken, joinUrl=joinUrl)


@kahoot.route('/join')
def join():
    pin = request.args.get('pin', '')
    return render_template('kahoot_join.html', pin=pin)


@kahoot.route('/play/<pin>')
def play(pin):
    game = kahootManager.getGame(pin)
    if game is None:
        return redirect(url_for('kahoot.join'))
    return render_template('kahoot_play.html', game=game, map=game.map)


# ----------------------------------------------------------------------
# Socket handlers
# ----------------------------------------------------------------------
def setupKahootSockets(socketio: SocketIO):

    def sendReveal(game: KahootGame):
        """Sluit de huidige vraag af en stuur de resultaten naar bord en spelers."""
        reveal = game.reveal()
        if reveal is None:
            return
        socketio.emit('kahootReveal', reveal, to=hostRoom(game.pin))
        for player in game.players.values():
            if player.sid is not None and player.connected:
                socketio.emit('kahootResult', game.playerResult(player), to=player.sid)

    def questionTimer(game: KahootGame, run: int):
        socketio.sleep(game.seconds + 0.5)
        if game.state == 'question' and game.questionRun == run:
            sendReveal(game)

    def startNextQuestion(game: KahootGame):
        if game.nextQuestion():
            socketio.emit('kahootQuestion', game.questionPayload(forHost=True), to=hostRoom(game.pin))
            socketio.emit('kahootQuestion', game.questionPayload(forHost=False), to=playerRoom(game.pin))
            socketio.emit('kahootAnswerCount', game.answeredCount(), to=hostRoom(game.pin))
            socketio.start_background_task(questionTimer, game, game.questionRun)
        else:
            game.finish()
            leaderboard = game.leaderboard()
            socketio.emit('kahootFinished', {'leaderboard': leaderboard}, to=hostRoom(game.pin))
            for player in game.players.values():
                if player.sid is not None and player.connected:
                    socketio.emit('kahootFinished', {
                        'score': player.score,
                        'rank': game.rankOf(player),
                        'players': len(game.players),
                        'leaderboard': leaderboard,
                    }, to=player.sid)

    def hostGameFromData(data) -> KahootGame | None:
        game = kahootManager.getGame((data or {}).get('pin'))
        if game is None or (data or {}).get('token') != game.hostToken:
            emit('kahootError', {'message': 'Je bent niet de host van deze quiz.', 'fatal': True})
            return None
        return game

    @socketio.on('kahootHost')
    def onHost(data):  # verwacht {'pin': str, 'token': str}
        game = hostGameFromData(data)
        if game is None:
            return
        game.hostSid = request.sid
        join_room(hostRoom(game.pin))
        emit('kahootState', game.hostState())

    @socketio.on('kahootJoin')
    def onJoin(data):  # verwacht {'pin': str, 'name': str}
        data = data or {}
        game = kahootManager.getGame(data.get('pin'))
        if game is None:
            emit('kahootError', {'message': 'Geen quiz gevonden met deze pincode.'})
            return
        try:
            player = game.addPlayer(str(data.get('name', '')))
        except ValueError as e:
            emit('kahootError', {'message': str(e)})
            return
        emit('kahootJoined', {'pin': game.pin, 'playerId': player.id, 'name': player.name})
        socketio.emit('kahootPlayers', game.playersPayload(), to=hostRoom(game.pin))

    @socketio.on('kahootRejoin')
    def onRejoin(data):  # verwacht {'pin': str, 'playerId': str}
        data = data or {}
        game = kahootManager.getGame(data.get('pin'))
        player = game.getPlayer(data.get('playerId')) if game else None
        if game is None or player is None:
            emit('kahootError', {'message': 'Deze quiz bestaat niet (meer).', 'fatal': True})
            return
        player.sid = request.sid
        player.connected = True
        join_room(playerRoom(game.pin))
        emit('kahootState', game.playerState(player))
        socketio.emit('kahootPlayers', game.playersPayload(), to=hostRoom(game.pin))

    @socketio.on('kahootStart')
    def onStart(data):  # verwacht {'pin': str, 'token': str}
        game = hostGameFromData(data)
        if game is None:
            return
        if game.state != 'lobby':
            return
        if not any(p.connected for p in game.players.values()):
            emit('kahootError', {'message': 'Er doet nog niemand mee.'})
            return
        startNextQuestion(game)

    @socketio.on('kahootNext')
    def onNext(data):  # verwacht {'pin': str, 'token': str}
        game = hostGameFromData(data)
        if game is None:
            return
        if game.state != 'reveal':
            return
        startNextQuestion(game)

    @socketio.on('kahootReveal')
    def onReveal(data):  # verwacht {'pin': str, 'token': str} — host sluit de vraag eerder af
        game = hostGameFromData(data)
        if game is None:
            return
        sendReveal(game)

    @socketio.on('kahootAnswer')
    def onAnswer(data):  # verwacht {'pin': str, 'playerId': str, 'answer': str, 'hashed': bool}
        data = data or {}
        game = kahootManager.getGame(data.get('pin'))
        if game is None:
            return
        accepted, everyoneAnswered = game.answer(
            data.get('playerId'), data.get('answer', ''), bool(data.get('hashed'))
        )
        if not accepted:
            emit('kahootAnswerRejected')
            return
        emit('kahootAnswerAck')
        socketio.emit('kahootAnswerCount', game.answeredCount(), to=hostRoom(game.pin))
        if everyoneAnswered:
            sendReveal(game)

    @socketio.on('disconnect')
    def onDisconnect(*args):
        game, player = kahootManager.findBySid(request.sid)
        if game is None:
            return
        if player is None:
            game.hostSid = None
            return
        player.connected = False
        socketio.emit('kahootPlayers', game.playersPayload(), to=hostRoom(game.pin))
        # Als de laatste speler die nog moest antwoorden wegvalt, hoeft niemand te wachten.
        if game.state == 'question':
            connected = [p for p in game.players.values() if p.connected]
            if connected and all(game.currentIndex in p.answers for p in connected):
                sendReveal(game)
