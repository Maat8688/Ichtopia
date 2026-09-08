"""Start de site lokaal, zonder Postgres en zonder Docker.

    cd app
    python dev.py

De echte site draait op Postgres. Om even snel iets te bekijken is dat
onhandig, dus dit script zet er een sqlite-bestandje naast. De tabel met
resultaten past niet in sqlite (die gebruikt kolommen van het type ARRAY),
maar de kaarten en de klassikale quiz hebben de database helemaal niet
nodig: alleen inloggen werkt hier niet.
"""
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
os.chdir(HIER)                 # de kaarten worden met een pad vanaf app/ gezocht
sys.path.insert(0, HIER)

os.environ.setdefault('SECRET_KEY', 'alleen-voor-lokaal-testen')
os.environ.setdefault('DATABASE_URL', 'sqlite:///' + os.path.join(HIER, 'dev.db'))
os.environ.setdefault('KAHOOT_HOST_CODE', 'docent')
os.environ.setdefault('LOG_DIR', os.path.join(HIER, 'log'))

# De tabellen aanmaken lukt niet in sqlite en is hier ook nergens voor nodig.
import flask_sqlalchemy
flask_sqlalchemy.SQLAlchemy.create_all = lambda self, *args, **kwargs: None

from src import app, socketio  # noqa: E402  (pas importeren als alles klaarstaat)

if __name__ == '__main__':
    poort = int(os.getenv('PORT', '5000'))
    print(f'Topo draait op http://127.0.0.1:{poort}')
    print(f'Docentcode voor de klassikale quiz: {os.environ["KAHOOT_HOST_CODE"]}')
    socketio.run(app, host='127.0.0.1', port=poort, debug=True,
                 allow_unsafe_werkzeug=True)
