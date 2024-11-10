from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_socketio import SocketIO, send, emit
from flask_login import login_user, login_required, logout_user, current_user
import sys
from . import sessionManager
from .models import User
from .map import mapSession, SessionGamemode, SessionManager

main = Blueprint('main', __name__)


@main.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        print(request.form, file=sys.stderr)
        if request.form.get('KaartInput') == 'Nederland':
            newSession = mapSession.fromSVG('data/maps/Nederland.svg', request.form.get('mode'), request.form.getlist('questions'))
        elif request.form.get('KaartInput') == 'Europa':
            newSession = mapSession.fromSVG('data/maps/Europa.svg', request.form.get('mode'), request.form.getlist('questions'))
        id = sessionManager.createSession(newSession)
        return redirect(url_for('main.learn', sessionToken=id))
    return render_template('index.html')

@main.route('/me')
@login_required
def me():
    print('me', file=sys.stderr)
    return 'me'

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.index'))
        flash('Invalid email or password', 'danger')
    return render_template('login.html')

@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.login'))

@main.route('/learn')
def learn():
    sessionToken = request.args.get('sessionToken')
    if sessionToken in sessionManager.sessions.keys():
        session = sessionManager.getSession(sessionToken)
        return render_template('learn.html', map=session)
    else:
        return redirect(url_for('main.index'))
    

@main.route('/host')
def host():
    print('host', file=sys.stderr)
    return 'host'

@main.route('/join')
def join():
    print('join', file=sys.stderr)
    return 'join'

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
            # emit('updateMap', {'questionId': questionId, 'status': 'correct'})
            emit('setMapState', session.getMapState())
        else:
            # emit('updateMap', {'questionId': questionId, 'status': 'incorrect'})
            emit('setMapState', session.getMapState())

        emit('setProgressBar', session.getProgresBar())

        if session.nextQuestion():
            # emit('finished', {'score': currentSession.score, 'totalGuesses': currentSession.totalGuesses})
            send(f"Finished with a score of {session.score}/{session.totalGuesses}")
            emit('finished', {"Overvieuw": session.getProgresBar()})
            return

        if session.sessionMode == 1:
            emit('question', {'question': session.hash(session.currentQuestion.id), 'mcAwnsers': session.mcAwnsers})
        elif session.sessionMode == 2:
            emit('question', {'question': session.hash(session.currentQuestion.id)})
        elif session.sessionMode == 3:
            emit('question', {'question': session.currentQuestion.id})

    @socketio.on('getQuestion')
    def getQuestion(data): # expects {'sessionToken': str}
        session:mapSession = sessionManager.getSession(data['sessionToken'])
        if session.sessionMode == 1:
            emit('question', {'question': session.hash(session.currentQuestion.id), 'mcAwnsers': session.mcAwnsers})
        elif session.sessionMode == 2:
            emit('question', {'question': session.hash(session.currentQuestion.id)})
        elif session.sessionMode == 3:
            emit('question', {'question': session.currentQuestion.id})

    @socketio.on('getProgressbar')
    def getProgressbar(data):
        session:mapSession = sessionManager.getSession(data['sessionToken'])
        emit('setProgressBar', session.getProgresBar())