from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_socketio import SocketIO, send, emit
from flask_login import login_user, login_required, logout_user, current_user
import sys
from . import sessionManager
from .models import User
from .map import mapSession, SessionGamemode, SessionManager
from .kahoot import MAP_FILES

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
    

# @app.route('/register', methods=['GET', 'POST'])
# def register():
#     if request.method == 'POST':
#         username = request.form.get('username')
#         password = request.form.get('password')

#         if not username or not password:
#             flash('Username and password are required.', 'error')
#             return render_template('register.html')

#         db = SQLDatabase()
#         try:
#             # Check if the username already exists in the database
#             if db.execute("SELECT id FROM users WHERE username = %s", (username,)):
#                 print("username alr exist")
#                 flash('Username is already in use. Please choose a different one.', 'error')
#                 return render_template('register.html')

#             # If username is not in use, proceed with registration
#             password_hash = generate_password_hash(password)
#             db.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, password_hash))
#             flash('Your account has been created! You can now login.', 'success')
#             return redirect(url_for('login'))
#         except IntegrityError:
#             flash('Username is already in use. Please choose a different one.', 'error')
#             return render_template('register.html')
#         except Exception as e:
#             flash('An error occurred during registration. Please try again.', 'error')
#             print(e)  # For debugging purposes, it might help to log or print the exception
#         finally:
#             db.close()

#     return render_template('pages/register.html')







def setupSockets(socketio: SocketIO):
    def haalSessie(data):
        """De sessie bij dit token, of None als hij is opgeruimd.

        Sessies worden na een paar uur stilte weggegooid, anders loopt het
        geheugen van de server vol. Wie daarna nog een antwoord instuurt,
        krijgt een melding in plaats van een pagina die niets meer doet.
        """
        session = sessionManager.getSession((data or {}).get('sessionToken'))
        if session is None:
            emit('sessieVerlopen')
            return None
        session.touch()
        return session

    @socketio.on('message')
    def handle_message(data):
        print('received message: ' + data)
        send(f'You said: {data}')

    @socketio.on('answerQuestion')
    def answerQuestion(data): # expects {'awnser': str, 'hashed': bool, 'sessionToken': str}
        session = haalSessie(data)
        if session is None:
            return
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
            print(session.getFinishedData(), file=sys.stderr)
            emit('finished', {"Overvieuw": session.getFinishedData()})
            return

        if session.sessionMode == 1:
            emit('question', {'question': session.hash(session.currentQuestion.id), 'mcAwnsers': session.mcAwnsers})
        elif session.sessionMode == 2:
            emit('question', {'question': session.hash(session.currentQuestion.id)})
        elif session.sessionMode == 3:
            emit('question', {'question': session.currentQuestion.displayName})

    @socketio.on('getQuestion')
    def getQuestion(data): # expects {'sessionToken': str}
        session = haalSessie(data)
        if session is None:
            return
        if session.sessionMode == 1:
            emit('question', {'question': session.hash(session.currentQuestion.id), 'mcAwnsers': session.mcAwnsers})
        elif session.sessionMode == 2:
            emit('question', {'question': session.hash(session.currentQuestion.id)})
        elif session.sessionMode == 3:
            emit('question', {'question': session.currentQuestion.displayName})

    @socketio.on('getProgressbar')
    def getProgressbar(data):
        session = haalSessie(data)
        if session is None:
            return
        emit('setProgressBar', session.getProgresBar())