"""Test dat `flask db upgrade` veilig is op een bestaande database.

Draaien vanuit de map `app`:

    python tests/test_migraties.py

Twee gevallen die allebei echt voorkomen:

1. Een database van voor deze branch: de tabel `user` bestaat, met de oude
   kolommen en zonder alembic-geschiedenis. Zo ziet de server van school
   eruit, en zo zag de docker-database lokaal er ook uit.
2. Een verse database, waar db.create_all() bij het opstarten alles al heeft
   aangemaakt. Dan moet upgrade gewoon niets doen in plaats van struikelen.

In allebei de gevallen mag er geen enkel account verdwijnen.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import Checks, loadApp   # noqa: E402

check = Checks()

OUDE_DATABASE = tempfile.mkstemp(suffix='.db')[1]

# De oude tabellen, precies zoals ze er voor deze branch uitzagen.
import sqlite3   # noqa: E402

verbinding = sqlite3.connect(OUDE_DATABASE)
verbinding.executescript('''
    CREATE TABLE "user" (
        id INTEGER NOT NULL PRIMARY KEY,
        username VARCHAR(80) NOT NULL UNIQUE,
        email VARCHAR(120) NOT NULL UNIQUE,
        password_hash VARCHAR(128) NOT NULL,
        account_type VARCHAR(7) NOT NULL
    );
    CREATE TABLE results (
        id INTEGER NOT NULL PRIMARY KEY,
        players TEXT NOT NULL,
        scores TEXT NOT NULL,
        date DATETIME NOT NULL,
        creator_id INTEGER NOT NULL REFERENCES "user" (id)
    );
    INSERT INTO "user" (username, email, password_hash, account_type)
    VALUES ('Kevin', 'kevin@example.com', 'scrypt:oud', 'TEACHER');
''')
verbinding.commit()
verbinding.close()

app = loadApp(DATABASE_URL='sqlite:///' + OUDE_DATABASE)

from flask_migrate import upgrade                      # noqa: E402
from src.models import User, db                        # noqa: E402


def kolommen(tabel):
    inspector = db.inspect(db.engine)
    return {kolom['name'] for kolom in inspector.get_columns(tabel)}


def tabellen():
    return set(db.inspect(db.engine).get_table_names())


# ----------------------------------------------------------------------
# 1. Bestaande database
# ----------------------------------------------------------------------
with app.app_context():
    check('bestaand account staat er nog na het opstarten',
          db.session.query(User.id).count() == 1)
    check('de oude tabel mist de nieuwe kolommen nog',
          'created_at' not in kolommen('user') and 'xp' not in kolommen('user'))

    upgrade()

    na = kolommen('user')
    check('created_at is toegevoegd', 'created_at' in na)
    check('xp en elo zijn toegevoegd',
          {'xp', 'xp_day', 'xp_today', 'rating',
           'duels_won', 'duels_lost', 'duels_drawn'} <= na)
    check('de duel-tabel bestaat', 'duel_match' in tabellen())
    check('de tabellen user en results staan er nog',
          {'user', 'results'} <= tabellen())

    kevin = User.query.filter_by(email='kevin@example.com').first()
    check('het bestaande account is niet verdwenen', kevin is not None)
    check('het account heeft een aanmaakdatum gekregen',
          kevin is not None and kevin.created_at is not None)
    check('het account begint op 0 XP en 1000 elo',
          kevin is not None and kevin.xp == 0 and kevin.rating == 1000)

    # Nog een keer draaien mag niets kapotmaken.
    upgrade()
    check('een tweede upgrade doet niets', db.session.query(User.id).count() == 1)

# ----------------------------------------------------------------------
# 2. Verse database (alles al door db.create_all() aangemaakt)
# ----------------------------------------------------------------------
for module in [m for m in sys.modules if m == 'src' or m.startswith('src.')]:
    del sys.modules[module]

versApp = loadApp()
from flask_migrate import upgrade as upgradeVers        # noqa: E402
from src.models import db as versDb                     # noqa: E402

with versApp.app_context():
    try:
        upgradeVers()
        check('upgrade op een verse database gaat goed', True)
    except Exception as e:                              # noqa: BLE001
        check('upgrade op een verse database gaat goed', False, e)
    check('alle tabellen staan er',
          {'user', 'results', 'duel_match'}
          <= set(versDb.inspect(versDb.engine).get_table_names()))

sys.exit(check.report())
