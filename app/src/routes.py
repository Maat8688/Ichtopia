from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_socketio import SocketIO, send, emit
from flask_login import login_user, login_required, logout_user, current_user
import sys
from . import socketio
from .models import User
from .map import mapSession

main = Blueprint('socket', __name__)

currentSession = None

@main.route('/')
def index():
    print('index', file=sys.stderr)
    global currentSession
    currentSession = mapSession.fromSVG('data/maps/Nederland.svg')
    return render_template('index.html', map=currentSession)

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
    def answerQuestion(data):
        global currentSession
        # emit('updateMap', {'questionId': data['questionId'], 'status': 'correct'})
        if currentSession.awnserQuestion(data['questionId'], True):
            emit('updateMap', {'questionId': data['questionId'], 'status': 'correct'})
            if currentSession.nextQuestion():
                # emit('finished', {'score': currentSession.score, 'totalGuesses': currentSession.totalGuesses})
                send(f"Finished with a score of {currentSession.score}/{currentSession.totalGuesses}")
                return
        else:
            emit('updateMap', {'questionId': data['questionId'], 'status': 'incorrect'})

        emit('question', {'question': currentSession.questions[currentSession.currentQuestion].id})
