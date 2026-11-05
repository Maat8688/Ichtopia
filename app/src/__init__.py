import os
import logging
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, request
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
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
LOG_DIR = os.getenv("LOG_DIR", "/app/log")
log_path = os.path.join(LOG_DIR, "access.log")

try:
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,   # 5 MB per file
        backupCount=5,
        encoding="utf-8",
    )
except OSError as e:
    # Bijvoorbeeld een log-map van root terwijl de app als gewone gebruiker
    # draait. Dan liever zonder logbestand opstarten dan helemaal niet.
    print(f"Kan {log_path} niet openen ({e}); log alleen naar de console.")
    file_handler = logging.StreamHandler()
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
# In docker-compose zit Caddy (https) voor de app en staat COOKIE_SECURE=1, zodat
# de inlogcookie nooit over gewoon http gaat. Lokaal zonder https: laat hem uit.
app.config['SESSION_COOKIE_SECURE'] = os.getenv('COOKIE_SECURE', '0') == '1'
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_SECURE'] = app.config['SESSION_COOKIE_SECURE']
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)

# Statische bestanden een uur laten bewaren door de browser. Zonder dit vraagt
# hij elke pagina opnieuw of het plaatje nog klopt: geen extra bytes, wel een
# extra rondje naar de server per bestand. Een uur, zodat een nieuwe versie na
# een update vanzelf wordt opgepikt.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 3600


# Elke link naar een statisch bestand krijgt ?v=<tijd van de laatste wijziging>.
# Verandert een css- of js-bestand na een update, dan verandert de link mee en
# haalt de browser meteen de nieuwe versie op, in plaats van nog een uur de
# oude te gebruiken.
@app.url_defaults
def statischeVersie(endpoint, values):
    if endpoint == 'static' and 'filename' in values and 'v' not in values:
        try:
            values['v'] = int(os.stat(os.path.join(app.static_folder, values['filename'])).st_mtime)
        except OSError:
            pass

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Bewust 'threading': de app draait onder gunicorn met een worker en meerdere
# threads (zie docker-compose.yaml). Alle quizzen en duels staan in het geheugen
# van dat ene proces, dus meer workers zou ze over processen verspreiden.
socketio = SocketIO(app, async_mode='threading')

# Achter een proxy (Caddy) is remote_addr altijd het adres van de proxy. Met
# TRUST_PROXY=1 nemen we het echte adres over uit X-Forwarded-For, maar alleen
# de laatste hop: die heeft Caddy zelf gezet en kan een bezoeker niet vervalsen.
# Zonder proxy ervoor moet dit uit blijven, anders kan iedereen zijn IP
# verzinnen en zo om de rem op wachtwoorden raden heen.
if os.getenv('TRUST_PROXY', '0') == '1':
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
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

    from .beheer import beheer
    app.register_blueprint(beheer)

    from .meldingen import meldingen
    app.register_blueprint(meldingen)

    # Een event heeft bij Flask-SocketIO maar een handler, dus verdelen we
    # 'disconnect' zelf over de modules die er iets mee moeten.
    from .sockets import dispatchDisconnect

    @socketio.on('disconnect')
    def onDisconnect(*args):
        dispatchDisconnect(request.sid)

    @app.after_request
    def logRequest(response):
        # De ontwikkelserver van Werkzeug schrijft zelf al zo'n regel; onder
        # gunicorn doen we het hier, in hetzelfde formaat, zodat monitor.py de
        # log kan blijven lezen. Met het echte IP dankzij ProxyFix.
        if not request.environ.get('SERVER_SOFTWARE', '').startswith('Werkzeug'):
            path = request.environ.get('RAW_URI') or request.full_path.rstrip('?')
            app.logger.info('%s - - [%s] "%s %s %s" %s -',
                            request.remote_addr or '-',
                            datetime.now().strftime('%d/%b/%Y %H:%M:%S'),
                            request.method, path,
                            request.environ.get('SERVER_PROTOCOL', 'HTTP/1.1'),
                            response.status_code)
        return response

    from .errors import registerErrorHandlers
    registerErrorHandlers(app)

    # Elke bekeken pagina tellen voor /statistieken (zie gebruik.py).
    from .gebruik import registreerBezoeken
    registreerBezoeken(app)

    from .models import db, User
    db.init_app(app)
    db.create_all()
    # create_all voegt geen kolommen toe aan een tabel die al bestaat; dat
    # doen we voor de tabel gebruik zelf (zie gebruik.py).
    from .gebruik import zorgVoorKolommen
    zorgVoorKolommen()
    migrate.init_app(app, db)

    # Vangnet voor als 'flask db upgrade' vergeten is (zie de migratie
    # e2b4c6d8f0a1): een account heeft geen e-mail meer, dus de kolom mag niet
    # meer verplicht zijn, en wat er nog in staat wordt gewist.
    def geenEmailMeer():
        from sqlalchemy import inspect, text
        try:
            kolommen = {k['name']: k for k in inspect(db.engine).get_columns('user')}
            email = kolommen.get('email')
            if email is None:
                return
            with db.engine.begin() as verbinding:
                if not email.get('nullable', True) and db.engine.dialect.name == 'postgresql':
                    verbinding.execute(text('ALTER TABLE "user" ALTER COLUMN email DROP NOT NULL'))
                if email.get('nullable', True) or db.engine.dialect.name == 'postgresql':
                    verbinding.execute(text('UPDATE "user" SET email = NULL WHERE email IS NOT NULL'))
        except Exception:
            app.logger.warning('E-mailkolom niet bijgewerkt; draai flask db upgrade', exc_info=True)

    geenEmailMeer()

    # De woorden die een beheerder op /beheer aan het naamfilter toevoegde.
    from .beheer import laadWoorden
    laadWoorden()

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    login_manager.login_message = 'Log eerst in om deze pagina te bekijken.'
    login_manager.session_protection = 'strong'
