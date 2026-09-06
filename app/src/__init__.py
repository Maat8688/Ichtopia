import os
import logging
from datetime import timedelta
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, request
from werkzeug.exceptions import HTTPException
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

from .map import SessionManager

app = Flask(
    __name__,
    template_folder='../templates',
    static_folder='../static',
)

# ---------------- LOGGING SETUP ----------------
LOG_DIR = "/app/log"  # matches Docker volume: -v ./logs:/app/logs
os.makedirs(LOG_DIR, exist_ok=True)

log_path = os.path.join(LOG_DIR, "access.log")

file_handler = RotatingFileHandler(
    log_path,
    maxBytes=5_000_000,   # 5 MB per file
    backupCount=5,
    encoding="utf-8",
)
file_handler.setLevel(logging.INFO)

# Log the Werkzeug-style access lines as plain text
formatter = logging.Formatter('%(message)s')
file_handler.setFormatter(formatter)

# Attach to Flask app logger
app.logger.setLevel(logging.INFO)
app.logger.addHandler(file_handler)

# Attach to Werkzeug (access) logger – this is where lines like
# "77.160.5.117 - - [..] "GET / HTTP/1.1" 200 -" come from
werkzeug_logger = logging.getLogger("werkzeug")
werkzeug_logger.setLevel(logging.INFO)
werkzeug_logger.addHandler(file_handler)
# ------------------------------------------------

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or os.urandom(32).hex()
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# De app zelf luistert op poort 80 (http), dus de cookie mag niet standaard
# https-only zijn. Draait er ooit een https-proxy voor: zet COOKIE_SECURE=1.
app.config['SESSION_COOKIE_SECURE'] = os.getenv('COOKIE_SECURE', '0') == '1'
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_SECURE'] = app.config['SESSION_COOKIE_SECURE']
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

socketio = SocketIO(app)
migrate = Migrate()
login_manager = LoginManager(app)
sessionManager = SessionManager()

with app.app_context():
    from .routes import main, setupSockets
    app.register_blueprint(main)
    setupSockets(socketio)

    from .kahoot_routes import kahoot, setupKahootSockets
    app.register_blueprint(kahoot)
    setupKahootSockets(socketio)

    from .auth import auth
    app.register_blueprint(auth)

    from .duel_routes import duel, setupDuelSockets
    app.register_blueprint(duel)
    setupDuelSockets(socketio)

    from .ranking import ranking
    app.register_blueprint(ranking)

    # Een event heeft bij Flask-SocketIO maar een handler, dus verdelen we
    # 'disconnect' zelf over de modules die er iets mee moeten.
    from .sockets import dispatchDisconnect

    @socketio.on('disconnect')
    def onDisconnect(*args):
        dispatchDisconnect(request.sid)

    from .errors import registerErrorHandlers
    registerErrorHandlers(app)

    from .models import db, User
    db.init_app(app)
    db.create_all()
    migrate.init_app(app, db)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    login_manager.login_message = 'Log eerst in om deze pagina te bekijken.'
    login_manager.session_protection = 'strong'
