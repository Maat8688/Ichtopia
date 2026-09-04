import os
import time
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template
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

    from .models import db, User
    db.init_app(app)

    # The database container may still be starting (or its DNS alias may not
    # resolve yet) when this module is imported. Retry rather than crash the
    # whole app, which `restart: always` would otherwise turn into a loop.
    _DB_CONNECT_ATTEMPTS = 10
    _DB_CONNECT_DELAY_SECONDS = 3

    def _is_retryable(exc):
        """True for "not up yet" errors, False for ones that will never fix themselves.

        SQLSTATE class 28 is "invalid authorization specification": a wrong
        password, or a role that does not exist in the cluster. Retrying that
        just delays a clear error message by half a minute.
        """
        pgcode = getattr(getattr(exc, "orig", exc), "pgcode", None)
        return not (pgcode and str(pgcode).startswith("28"))

    for _attempt in range(1, _DB_CONNECT_ATTEMPTS + 1):
        try:
            db.create_all()
            break
        except Exception as exc:  # noqa: BLE001 - driver/DNS errors are retryable here
            if not _is_retryable(exc):
                app.logger.error(
                    "Database rejected our credentials, not retrying. Check that "
                    "POSTGRES_USER/POSTGRES_PASSWORD match the role stored in the "
                    "postgres_data volume: %s",
                    exc,
                )
                raise
            if _attempt == _DB_CONNECT_ATTEMPTS:
                app.logger.error(
                    "Database unreachable after %s attempts: %s",
                    _DB_CONNECT_ATTEMPTS,
                    exc,
                )
                raise
            app.logger.warning(
                "Database not ready (attempt %s/%s): %s",
                _attempt,
                _DB_CONNECT_ATTEMPTS,
                exc,
            )
            time.sleep(_DB_CONNECT_DELAY_SECONDS)

    migrate.init_app(app, db)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    login_manager.login_view = 'socket.login'
    login_manager.login_message_category = 'info'
    login_manager.login_message = 'Please log in to access this page.'
