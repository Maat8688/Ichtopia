import os
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template
from flask_socketio import SocketIO

# ---------------- DATABASE / ACCOUNTS UITGESCHAKELD ----------------
# De site draait volledig zonder database. Het spel houdt zijn state in het
# geheugen (SessionManager in map.py), en de publieke routes /, /learn, /host
# en /join raakten Postgres sowieso nooit aan. Alleen inloggen gebruikte de
# database, en die routes waren al stuk: login.html post naar
# url_for('socket.login') terwijl de blueprint 'main' heet.
#
# Weer aanzetten? Haal het commentaar hier en in routes.py weg, zet de
# pakketten terug in requirements.txt en de db-service terug in
# docker-compose.yaml. De login_view hieronder is meteen gecorrigeerd naar
# 'main.login', dus die bug komt niet terug.
#
# from flask_sqlalchemy import SQLAlchemy
# from flask_migrate import Migrate
# from flask_login import LoginManager
# -------------------------------------------------------------------

from .map import SessionManager

app = Flask(
    __name__,
    template_folder='../templates',
    static_folder='../static',
)

# ---------------- LOGGING SETUP ----------------
LOG_DIR = "/app/log"  # provided by the `.:/app` bind mount in docker-compose.yaml
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

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
# app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

socketio = SocketIO(app)
# migrate = Migrate()
# login_manager = LoginManager(app)
sessionManager = SessionManager()

with app.app_context():
    from .routes import main, setupSockets
    app.register_blueprint(main)
    setupSockets(socketio)

    # from .models import db, User
    # db.init_app(app)
    # db.create_all()
    # migrate.init_app(app, db)
    #
    # @login_manager.user_loader
    # def load_user(user_id):
    #     return User.query.get(int(user_id))
    #
    # login_manager.login_view = 'main.login'
    # login_manager.login_message_category = 'info'
    # login_manager.login_message = 'Please log in to access this page.'
