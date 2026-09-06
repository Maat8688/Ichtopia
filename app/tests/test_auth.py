"""Rooktest van het accountsysteem.

Draaien vanuit de map `app`:

    python tests/test_auth.py

Gebruikt een tijdelijke SQLite-database, zodat er geen Postgres nodig is. De
tabel `results` gebruikt een Postgres-array; die wordt hieronder voor SQLite
als tekst weggeschreven, puur om de tabellen te kunnen aanmaken.
"""
import os, re, sys, tempfile

os.environ['DATABASE_URL'] = 'sqlite:///' + tempfile.mkstemp(suffix='.db')[1]
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['KAHOOT_HOST_CODE'] = 'docent123'

from sqlalchemy.ext.compiler import compiles
from sqlalchemy import ARRAY

@compiles(ARRAY, "sqlite")
def _array_as_text(element, compiler, **kw):  # alleen nodig voor deze test
    return "TEXT"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import app
app.config['TESTING'] = True

def token(html):
    m = re.search(r'name="csrfToken" value="([^"]+)"', html)
    assert m, 'geen csrf-token in formulier'
    return m.group(1)

fails = []
def check(name, cond, extra=''):
    print(('OK   ' if cond else 'FOUT ') + name + ('' if cond else ' :: ' + str(extra)[:300]))
    if not cond:
        fails.append(name)

c = app.test_client()

# --- registreren ---
r = c.get('/registreren')
check('GET /registreren', r.status_code == 200, r.status_code)
t = token(r.get_data(as_text=True))

r = c.post('/registreren', data={'csrfToken': 'fout', 'username': 'Floris', 'email': 'f@example.com',
                                 'password': 'wachtwoord1', 'passwordRepeat': 'wachtwoord1',
                                 'accountType': 'student'})
check('CSRF wordt geweigerd', 'verlopen' in r.get_data(as_text=True))

r = c.post('/registreren', data={'csrfToken': t, 'username': 'Floris', 'email': 'f@example.com',
                                 'password': 'kort', 'passwordRepeat': 'kort',
                                 'accountType': 'student'})
check('te kort wachtwoord geweigerd', 'minstens 8 tekens' in r.get_data(as_text=True))

r = c.post('/registreren', data={'csrfToken': t, 'username': 'Floris', 'email': 'f@example.com',
                                 'password': 'wachtwoord1', 'passwordRepeat': 'wachtwoord2',
                                 'accountType': 'student'})
check('ongelijke wachtwoorden geweigerd', 'niet gelijk' in r.get_data(as_text=True))

r = c.post('/registreren', data={'csrfToken': t, 'username': 'Floris', 'email': 'f@example.com',
                                 'password': 'wachtwoord1', 'passwordRepeat': 'wachtwoord1',
                                 'accountType': 'docent', 'teacherCode': 'fout'})
check('foute docentcode geweigerd', 'docentcode klopt niet' in r.get_data(as_text=True))

r = c.post('/registreren', data={'csrfToken': t, 'username': 'Floris', 'email': 'F@Example.com ',
                                 'password': 'wachtwoord1', 'passwordRepeat': 'wachtwoord1',
                                 'accountType': 'student'}, follow_redirects=True)
body = r.get_data(as_text=True)
check('registreren lukt', 'Mijn account' in body, body[:400])
check('e-mail in kleine letters', 'f@example.com' in body)
check('leerling-account', 'Leerling' in body)

# dubbel adres
c2 = app.test_client()
t2 = token(c2.get('/registreren').get_data(as_text=True))
r = c2.post('/registreren', data={'csrfToken': t2, 'username': 'Ander', 'email': 'f@example.com',
                                  'password': 'wachtwoord1', 'passwordRepeat': 'wachtwoord1',
                                  'accountType': 'student'})
check('dubbel e-mailadres geweigerd', 'bestaat al' in r.get_data(as_text=True))

# --- uitloggen ---
r = c.get('/account')
t3 = token(r.get_data(as_text=True))
r = c.post('/uitloggen', data={'csrfToken': t3}, follow_redirects=True)
check('uitloggen lukt', 'Inloggen' in r.get_data(as_text=True))
r = c.get('/account')
check('/account beschermd na uitloggen', r.status_code == 302 and '/inloggen' in r.headers['Location'],
      r.headers.get('Location'))

# --- inloggen ---
r = c.get('/inloggen')
t4 = token(r.get_data(as_text=True))
r = c.post('/inloggen', data={'csrfToken': t4, 'email': 'f@example.com', 'password': 'fout'})
check('fout wachtwoord geweigerd', 'klopt niet' in r.get_data(as_text=True))
r = c.post('/inloggen', data={'csrfToken': t4, 'email': 'f@example.com', 'password': 'wachtwoord1'},
           follow_redirects=True)
check('inloggen lukt', 'Topo' in r.get_data(as_text=True) and r.status_code == 200)
r = c.get('/account')
check('/account bereikbaar na inloggen', r.status_code == 200 and 'Floris' in r.get_data(as_text=True))
check('naam in de topbar', 'Floris' in c.get('/').get_data(as_text=True))

# --- open redirect ---
c3 = app.test_client()
t5 = token(c3.get('/inloggen').get_data(as_text=True))
r = c3.post('/inloggen?next=https://evil.example.com/x',
            data={'csrfToken': t5, 'email': 'f@example.com', 'password': 'wachtwoord1'})
check('geen open redirect', 'evil.example.com' not in r.headers.get('Location', ''), r.headers.get('Location'))

# --- rem op gokken ---
c4 = app.test_client()
for i in range(6):
    t6 = token(c4.get('/inloggen').get_data(as_text=True))
    r = c4.post('/inloggen', data={'csrfToken': t6, 'email': 'f@example.com', 'password': 'fout'})
check('rem na 5 pogingen', 'Te veel mislukte pogingen' in r.get_data(as_text=True))

# --- docentaccount ---
c5 = app.test_client()
t7 = token(c5.get('/registreren').get_data(as_text=True))
r = c5.post('/registreren', data={'csrfToken': t7, 'username': 'Docent Jansen', 'email': 'd@example.com',
                                  'password': 'wachtwoord1', 'passwordRepeat': 'wachtwoord1',
                                  'accountType': 'docent', 'teacherCode': 'docent123'},
            follow_redirects=True)
check('docentaccount aanmaken', 'Docent' in r.get_data(as_text=True))
r = c5.get('/host')
check('docent mag de klassikale quiz hosten', r.status_code == 200, r.status_code)

# oude /login-link blijft werken
r = app.test_client().get('/login')
check('/login stuurt door naar /inloggen', r.status_code == 302 and r.headers['Location'].endswith('/inloggen'), r.headers.get('Location'))

print('\n' + ('ALLES GOED' if not fails else 'MISLUKT: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
