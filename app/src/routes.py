from flask import Blueprint, render_template, request, redirect, url_for
from flask_socketio import SocketIO, send, emit
from flask_login import current_user
from . import app, sessionManager
from .map import mapSession, SessionGamemode, SessionManager
from .kahoot import MAP_FILES
from .models import User, db
from .progress import XP_DAILY_CAP, practiceXp

main = Blueprint('main', __name__)


@main.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        kaart = request.form.get('KaartInput')
        if kaart not in MAP_FILES:
            return redirect(url_for('main.index'))
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
    sessionToken = request.args.get('sessionToken')
    if sessionToken in sessionManager.sessions.keys():
        session = sessionManager.getSession(sessionToken)
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
    @socketio.on('message')
    def handle_message(data):
        print('received message: ' + data)
        send(f'You said: {data}')

    @socketio.on('answerQuestion')
    def answerQuestion(data): # expects {'awnser': str, 'hashed': bool, 'sessionToken': str}
        session:mapSession = sessionManager.getSession(data['sessionToken'])
        questionId = session.hash(session.currentQuestion.id) 

        if session.awnserQuestion(data['awnser'], data['hashed']):
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
        session:mapSession = sessionManager.getSession(data['sessionToken'])
        if session.sessionMode == 1:
            emit('question', {'question': session.hash(session.currentQuestion.id), 'mcAwnsers': session.mcAwnsers})
        elif session.sessionMode == 2:
            emit('question', {'question': session.hash(session.currentQuestion.id)})
        elif session.sessionMode == 3:
            emit('question', {'question': session.currentQuestion.displayName})

    @socketio.on('getProgressbar')
    def getProgressbar(data):
        session:mapSession = sessionManager.getSession(data['sessionToken'])
        emit('setProgressBar', session.getProgresBar())