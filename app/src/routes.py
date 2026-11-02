from flask import Blueprint, abort, render_template, request, redirect, url_for
from flask_socketio import SocketIO, send, emit
from flask_login import current_user
from . import app, sessionManager
from .map import mapSession, SessionGamemode, SessionManager
from .kahoot import MAP_FILES
from .models import User, db
from .progress import XP_DAILY_CAP, practiceXp
from .security import AttemptLimiter, clientIp

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
        id = sessionManager.createSession(newSession)
        return redirect(url_for('main.learn', sessionToken=id))
    return render_template('index.html')

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
        if not isinstance(data, dict):
            return None
        session = sessionManager.findSession(data.get('sessionToken'))
        if session is None:
            emit('sessionExpired')
        return session

    @socketio.on('answerQuestion')
    def answerQuestion(data): # expects {'awnser': str, 'hashed': bool, 'sessionToken': str}
        session = sessionFrom(data)
        if session is None or session.currentQuestion is None:
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
            emit('finished', {"Overvieuw": session.getFinishedData(),
                              "xp": awardPracticeXp(session)})
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
        if session is None or session.currentQuestion is None:
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
        emit('setProgressBar', session.getProgresBar())