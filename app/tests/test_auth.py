"""Rooktest van het accountsysteem.

Draaien vanuit de map `app`:

    python tests/test_auth.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import Checks, csrf as token, loadApp   # noqa: E402

app = loadApp()

check = Checks()

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
r = c5.post('/registreren', data={'csrfToken': t7, 'username': 'Kevin', 'email': 'd@example.com',
                                  'password': 'wachtwoord1', 'passwordRepeat': 'wachtwoord1',
                                  'accountType': 'docent', 'teacherCode': 'docent123'},
            follow_redirects=True)
body = r.get_data(as_text=True)
check('docentaccount aanmaken', 'Mijn account' in body and 'Docent' in body, body[:300])
r = c5.get('/host')
check('docent mag de klassikale quiz hosten', r.status_code == 200, r.status_code)

# oude /login-link blijft werken
r = app.test_client().get('/login')
check('/login stuurt door naar /inloggen', r.status_code == 302 and r.headers['Location'].endswith('/inloggen'), r.headers.get('Location'))

sys.exit(check.report())
