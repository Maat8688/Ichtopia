"""Test van de toetsmodus.

Draaien vanuit de map `app`:

    python tests/test_toets.py

Een toets wordt helemaal gespeeld via de socketverbinding.
"""
import os
import sys
import tempfile

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HIER)
sys.path.insert(0, HIER)
os.environ.update(SECRET_KEY='test', KAHOOT_HOST_CODE='docent', GEO_DB='/bestaat/niet.mmdb',
                  DATABASE_URL='sqlite:///' + tempfile.mkstemp(suffix='.db')[1], LOG_DIR=tempfile.mkdtemp())

import flask_sqlalchemy  # noqa: E402
flask_sqlalchemy.SQLAlchemy.create_all = lambda self, *a, **k: None   # zie dev.py

from src import app, gebruik, sessionManager, socketio  # noqa: E402
from src.map import mapSession  # noqa: E402
from src.models import Gebruik, db  # noqa: E402

with app.app_context():
    Gebruik.__table__.create(db.engine, checkfirst=True)

fouten = []


def check(naam, ok, extra=''):
    print(('OK   ' if ok else 'FOUT ') + naam + ('' if ok else ' :: ' + str(extra)[:300]))
    if not ok:
        fouten.append(naam)


BROWSER = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36',
           'Accept-Language': 'nl-NL'}

# --- Het rekenwerk ---------------------------------------------------------
s = mapSession.fromSVG('data/maps/Europa.svg', 'MultipleChoise', ['Landen'])
s.startToets(10)
check('toets van 10 vragen', s.toets and s.toetsTotaal == 10)
gezien = set()
for i in range(10):
    gezien.add(s.currentQuestion.id)
    antwoord = s.currentQuestion.allAnswers[0] if i < 7 else 'Atlantis'
    s.beantwoordToets(antwoord, False)
    klaar = s.volgendeToetsvraag()
    check(f'na vraag {i + 1}: {"klaar" if i == 9 else "nog niet klaar"}', klaar == (i == 9))
check('elke vraag precies een keer', len(gezien) == 10)
u = s.toetsUitslag()
check('7 van 10 goed', (u['goed'], u['totaal']) == (7, 10), u)
check('cijfer 1 + 9 x 7/10 = 7,3', u['cijfer'] == 7.3, u['cijfer'])
check('voldoende', u['voldoende'])
check('drie fouten met het gegeven antwoord', len(u['fouten']) == 3 and all(f['gegeven'] == 'Atlantis' for f in u['fouten']))

alles = mapSession.fromSVG('data/maps/Europa.svg', 'MultipleChoise', ['Landen'])
alles.startToets(None)
check('alle vragen', alles.toetsTotaal == len(alles.questions))
veel = mapSession.fromSVG('data/maps/Europa.svg', 'MultipleChoise', ['Landen'])
veel.startToets(500)
check('meer gevraagd dan er zijn: alle', veel.toetsTotaal == len(veel.questions))
for _ in range(veel.toetsTotaal):
    veel.beantwoordToets('fout', False)
    veel.volgendeToetsvraag()
check('alles fout is een 1', veel.toetsUitslag()['cijfer'] == 1.0)

klik = mapSession.fromSVG('data/maps/Europa.svg', 'ClickTheCountry', ['Landen'])
klik.startToets(2)
juist = klik.currentQuestion
klik.beantwoordToets(klik.hash(juist.id), True)
klik.volgendeToetsvraag()
ander = next(q for q in klik.questions if q is not klik.currentQuestion)
klik.beantwoordToets(klik.hash(ander.id), True)
klik.volgendeToetsvraag()
u = klik.toetsUitslag()
check('aanwijzen: goed herkend', u['goed'] == 1, u)
check('aanwijzen: bij fout staat welke plek je aanklikte', u['fouten'][0]['gegeven'] == ander.displayName, u['fouten'])

# --- Een hele toets via de website -----------------------------------------
c = app.test_client()
html = c.get('/', headers=BROWSER).get_data(as_text=True)
check('startpagina heeft de keuze toets', 'name="soort" value="toets"' in html and 'toetsVragen' in html)
r = c.post('/', headers=BROWSER, data={'KaartInput': 'Nederland', 'mode': 'MultipleChoise',
                                       'questions': ['Provincies'], 'soort': 'toets', 'toetsVragen': '10'})
token = r.headers['Location'].split('sessionToken=')[1]
from urllib.parse import unquote  # noqa: E402
token = unquote(token)
sessie = sessionManager.getSession(token)
check('sessie is een toets van 10', sessie.toets and sessie.toetsTotaal == 10)
check('oefenpagina toont het uitslagblok', 'id="toetsUitslag"' in c.get(r.headers['Location']).get_data(as_text=True))

sok = socketio.test_client(app)
sok.emit('getQuestion', {'sessionToken': token})
ontvangen = sok.get_received()
check('eerste vraag en voortgang', [m['name'] for m in ontvangen] == ['toetsVoortgang', 'question'],
      [m['name'] for m in ontvangen])
verklapt = []
for i in range(10):
    antwoord = sessie.currentQuestion.allAnswers[0] if i != 4 else 'Atlantis'
    sok.emit('answerQuestion', {'sessionToken': token, 'awnser': antwoord, 'hashed': False})
    namen = [m['name'] for m in sok.get_received()]
    verklapt += [n for n in namen if n in ('questionCorrect', 'questionIncorrect', 'setProgressBar')]
    if i < 9:
        check(f'vraag {i + 2} komt binnen', 'question' in namen, namen)
    else:
        laatste = namen
check('tussendoor niets verklapt', not verklapt, verklapt)
check('aan het eind de kaart en de uitslag', 'setMapState' in laatste and 'toetsKlaar' in laatste, laatste)
sok.emit('answerQuestion', {'sessionToken': token, 'awnser': 'x', 'hashed': False})
check('antwoord na afloop verandert niets', sessie.toetsUitslag()['goed'] == 9)
sok.emit('getQuestion', {'sessionToken': token})
check('opnieuw verbinden na afloop: weer de uitslag', 'toetsKlaar' in [m['name'] for m in sok.get_received()])

with app.app_context():
    rijen = Gebruik.query.filter_by(soort='oefenen_klaar').all()
    check('een keer opgeslagen, met cijfer', len(rijen) == 1 and rijen[0].toets and rijen[0].cijfer == 91,
          [(r.toets, r.cijfer) for r in rijen])
    o = gebruik.overzicht('7')
    check('statistieken: toets apart geteld', o['toetsen']['gemaakt'] == 1 and o['toetsen']['gemiddeld'] == 9.1,
          o['toetsen'])
    check('telt niet mee als oefensessie', o['tegels']['gestart'] == 0 and o['tegels']['afgerond'] == 0, o['tegels'])

c.post('/host/login', data={'code': 'docent'})
html = c.get('/statistieken').get_data(as_text=True)
check('statistiekenpagina toont de toetsen', '<h2>Toetsen</h2>' in html and '9,1' in html)

print('\n' + ('ALLES GOED' if not fouten else 'MISLUKT: ' + ', '.join(fouten)))
sys.exit(1 if fouten else 0)
