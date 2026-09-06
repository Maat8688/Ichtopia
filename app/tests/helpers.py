"""Gedeelde opzet voor de tests.

De app draait hier op een tijdelijke SQLite-database, zodat er geen Postgres
nodig is om te testen. De tabel `results` gebruikt een Postgres-array; die
wordt hieronder voor SQLite als tekst weggeschreven, puur om de tabellen te
kunnen aanmaken.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def loadApp(**env):
    """Importeer de app met een schone testdatabase. Geeft de Flask-app terug."""
    os.environ.setdefault('SECRET_KEY', 'test-secret')
    os.environ.setdefault('KAHOOT_HOST_CODE', 'docent123')
    os.environ['DATABASE_URL'] = 'sqlite:///' + tempfile.mkstemp(suffix='.db')[1]
    os.environ.update(env)

    from sqlalchemy import ARRAY
    from sqlalchemy.ext.compiler import compiles

    @compiles(ARRAY, 'sqlite')
    def _arrayAsText(element, compiler, **kw):   # alleen nodig voor deze test
        return 'TEXT'

    sys.path.insert(0, ROOT)
    from src import app
    app.config['TESTING'] = True
    return app


def csrf(html: str) -> str:
    match = re.search(r'name="csrfToken" value="([^"]+)"', html)
    assert match, 'geen csrf-token in het formulier'
    return match.group(1)


def register(client, username: str, email: str, password: str = 'wachtwoord1',
             accountType: str = 'student', teacherCode: str = ''):
    """Maak een account aan en log er meteen mee in."""
    token = csrf(client.get('/registreren').get_data(as_text=True))
    response = client.post('/registreren', data={
        'csrfToken': token, 'username': username, 'email': email,
        'password': password, 'passwordRepeat': password,
        'accountType': accountType, 'teacherCode': teacherCode,
    }, follow_redirects=True)
    body = response.get_data(as_text=True)
    assert 'Mijn account' in body, f'registreren van {username} mislukt: {body[:300]}'
    return response


class Checks:
    """Kleine testteller, zodat een testbestand zonder pytest kan draaien."""

    def __init__(self):
        self.failed: list[str] = []

    def __call__(self, name, condition, extra=''):
        print(('OK   ' if condition else 'FOUT ') + name
              + ('' if condition else ' :: ' + str(extra)[:300]))
        if not condition:
            self.failed.append(name)

    def report(self) -> int:
        print('\n' + ('ALLES GOED' if not self.failed
                      else 'MISLUKT: ' + ', '.join(self.failed)))
        return 1 if self.failed else 0
