"""Start de site lokaal, zonder Postgres en zonder Docker.

    cd app
    python dev.py

De echte site draait op Postgres. Om even snel iets te bekijken is dat
onhandig, dus dit script zet er een sqlite-bestandje naast. De tabel met
resultaten gebruikt een kolom van het type ARRAY, die sqlite niet kent; die
wordt hier als tekst aangemaakt. Zo werkt alles, ook inloggen, duels en de
ranglijst.
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

from sqlalchemy import ARRAY  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(ARRAY, 'sqlite')
def _arrayAlsTekst(element, compiler, **kw):   # alleen voor lokaal
    return 'TEXT'


from src import app, socketio  # noqa: E402  (pas importeren als alles klaarstaat)

if __name__ == '__main__':
    poort = int(os.getenv('PORT', '5000'))
    print(f'Ichtopia draait op http://127.0.0.1:{poort}')
    print(f'Docentcode voor de klassikale quiz: {os.environ["KAHOOT_HOST_CODE"]}')
    socketio.run(app, host='127.0.0.1', port=poort, debug=True,
                 allow_unsafe_werkzeug=True)
