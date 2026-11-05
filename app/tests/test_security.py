"""Test van de beveiliging rond het openbaar zetten.

Draaien vanuit de map `app`:

    python tests/test_security.py

- oefensessies hebben een maximum en verlopen;
- een rem op het aanmaken van oefensessies;
- een onbekend of verlopen sessietoken laat de socket niet crashen;
- formulieren van duel en docentpagina vragen een csrf-token;
- X-Forwarded-For telt alleen mee met TRUST_PROXY=1.
"""
import os
import subprocess
import sys
import textwrap
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import ROOT, Checks, csrf, loadApp   # noqa: E402

app = loadApp()

from src import socketio, sessionManager   # noqa: E402
from src import routes                     # noqa: E402
from src.map import SessionManager         # noqa: E402

check = Checks()

# ----------------------------------------------------------------------
# SessionManager: maximum en verlopen
# ----------------------------------------------------------------------
manager = SessionManager(maxSessions=3, maxIdle=60)
ids = [manager.createSession(f'sessie{i}') for i in range(3)]
check('tokens zijn lang en willekeurig', len(set(ids)) == 3 and all(len(i) >= 30 for i in ids))
manager.findSession(ids[0])                # de oudste weer gebruiken
nieuw = manager.createSession('sessie3')
check('vol: de langst niet gebruikte gaat eruit',
      manager.findSession(ids[1]) is None and manager.findSession(ids[0]) == 'sessie0')
check('nooit meer dan het maximum', len(manager.sessions) == 3)
check('nieuwe sessie staat erin', manager.findSession(nieuw) == 'sessie3')

manager._lastUsed[ids[2]] = time.time() - 120
check('te lang niet gebruikt is verlopen', manager.findSession(ids[2]) is None)
check('onzin als token geeft None', manager.findSession(None) is None
      and manager.findSession(['x']) is None and manager.findSession('bestaatniet') is None)

# ----------------------------------------------------------------------
# Oefenen via de site
# ----------------------------------------------------------------------
client = app.test_client()
start = {'KaartInput': 'Nederland', 'mode': 'MultipleChoise', 'questions': ['Provincies']}
response = client.post('/', data=start)
check('oefening starten werkt', response.status_code == 302 and 'sessionToken=' in response.headers['Location'],
      response.status_code)

routes.practiceLimiter.maxAttempts = 3
routes.practiceLimiter.reset('127.0.0.1')
codes = [client.post('/', data=start).status_code for _ in range(4)]
check('na te veel nieuwe oefeningen volgt 429', codes == [302, 302, 302, 429], codes)
check('429 heeft een nette pagina', 'Even rustig aan' in client.post('/', data=start).get_data(as_text=True))
routes.practiceLimiter.maxAttempts = 200
routes.practiceLimiter.reset('127.0.0.1')

check('onbekend token op /learn stuurt terug', client.get('/learn?sessionToken=nope').status_code == 302)

socket = socketio.test_client(app, flask_test_client=client)
for event, data in [('answerQuestion', {'sessionToken': 'nope', 'awnser': 'x', 'hashed': False}),
                    ('getQuestion', {'sessionToken': 'nope'}),
                    ('getProgressbar', {}),
                    ('getQuestion', 'geen dict')]:
    socket.emit(event, data)
names = [m['name'] for m in socket.get_received()]
check('onbekend token: sessionExpired in plaats van een crash',
      names.count('sessionExpired') == 3, names)
check('socket is nog verbonden', socket.is_connected())

# ----------------------------------------------------------------------
# CSRF op de formulieren die het nog niet hadden
# ----------------------------------------------------------------------
teacher = app.test_client()
body = teacher.post('/host/login', data={'code': 'docent123'}).get_data(as_text=True)
check('docentcode zonder token wordt geweigerd', 'verlopen' in body)
token = csrf(teacher.get('/host/login').get_data(as_text=True))
response = teacher.post('/host/login', data={'code': 'docent123', 'csrfToken': token})
check('docentcode met token werkt', response.status_code == 302, response.status_code)

body = teacher.post('/host', data={'KaartInput': 'Nederland', 'questions': ['Provincies']}).get_data(as_text=True)
check('quiz aanmaken zonder token wordt geweigerd', 'verlopen' in body)
token = csrf(teacher.get('/host').get_data(as_text=True))
response = teacher.post('/host', data={'csrfToken': token, 'KaartInput': 'Nederland',
                                       'mode': 'MultipleChoise', 'questions': ['Provincies']})
check('quiz aanmaken met token werkt', response.status_code == 302, response.status_code)

# ----------------------------------------------------------------------
# X-Forwarded-For
# ----------------------------------------------------------------------
from src.security import clientIp   # noqa: E402

with app.test_request_context('/', headers={'X-Forwarded-For': '6.6.6.6'},
                              environ_base={'REMOTE_ADDR': '10.0.0.1'}):
    check('zonder TRUST_PROXY telt X-Forwarded-For niet', clientIp() == '10.0.0.1', clientIp())

# Met TRUST_PROXY=1 in een los proces, omdat de instelling bij het importeren
# wordt gelezen. Caddy voegt het echte IP achteraan toe; een verzonnen adres
# ervoor mag niet meetellen.
script = textwrap.dedent('''
    import sys
    sys.path.insert(0, 'tests')
    from helpers import loadApp
    app = loadApp(TRUST_PROXY='1')
    from flask import request
    from src.security import clientIp

    @app.route('/_ip')
    def _ip():
        return clientIp() + ' ' + request.scheme

    client = app.test_client()
    print(client.get('/_ip', headers={'X-Forwarded-For': '6.6.6.6, 1.2.3.4',
                                      'X-Forwarded-Proto': 'https'}).get_data(as_text=True))
''')
result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, capture_output=True, text=True)
lastLine = (result.stdout.strip().splitlines() or [''])[-1]
check('met TRUST_PROXY telt alleen de laatste hop', lastLine == '1.2.3.4 https',
      result.stdout[-300:] + result.stderr[-500:])

sys.exit(check.report())
