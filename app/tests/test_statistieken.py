"""Test van /statistieken en het bijhouden van gebruik.

Draaien vanuit de map `app`:

    python tests/test_statistieken.py

Draait op een tijdelijke sqlite-database, net als dev.py.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HIER)
sys.path.insert(0, HIER)
os.environ['SECRET_KEY'] = 'test'
os.environ['KAHOOT_HOST_CODE'] = 'docent'
os.environ['DATABASE_URL'] = 'sqlite:///' + tempfile.mkstemp(suffix='.db')[1]
os.environ['LOG_DIR'] = tempfile.mkdtemp()

import flask_sqlalchemy  # noqa: E402
flask_sqlalchemy.SQLAlchemy.create_all = lambda self, *a, **k: None   # zie dev.py

from src import app  # noqa: E402
from src import gebruik  # noqa: E402
from src.models import Gebruik, db  # noqa: E402

with app.app_context():
    Gebruik.__table__.create(db.engine, checkfirst=True)

fouten = []


def check(naam, ok, extra=''):
    print(('OK   ' if ok else 'FOUT ') + naam + ('' if ok else ' :: ' + str(extra)[:300]))
    if not ok:
        fouten.append(naam)


def rijen(soort=None):
    with app.app_context():
        q = Gebruik.query
        if soort:
            q = q.filter_by(soort=soort)
        return q.all()


telefoon = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148',
            'Accept-Language': 'nl-NL,nl;q=0.9'}
c = app.test_client()

# --- Afgeschermd ---------------------------------------------------------
r = c.get('/statistieken')
check('zonder docentcode: doorgestuurd', r.status_code == 302 and '/host/login' in r.headers['Location'])
check('json ook afgeschermd', c.get('/statistieken.json').status_code == 302)

# --- Bezoeken tellen -----------------------------------------------------
c.get('/', headers=telefoon)
c.get('/join', headers=telefoon)
c.get('/static/css/main.css')
c.get('/bestaat-niet')
bezoeken = rijen('bezoek')
check('twee echte pagina\'s geteld, geen css of 404', [b.pagina for b in bezoeken] == ['Startpagina', 'Meedoen aan quiz'],
      [b.pagina for b in bezoeken])
check('apparaat herkend als telefoon', all(b.apparaat == 'telefoon' for b in bezoeken))
check('zelfde bezoeker, zelfde code vandaag', len({b.bezoeker for b in bezoeken}) == 1)
alles = json.dumps([{k: str(getattr(b, k)) for k in ('bezoeker', 'pagina', 'apparaat')} for b in rijen()])
check('geen IP-adres opgeslagen', '127.0.0.1' not in alles)

# --- Oefensessie ---------------------------------------------------------
r = c.post('/', data={'KaartInput': 'Europa', 'mode': 'MultipleChoise', 'questions': ['Landen']}, headers=telefoon)
check('oefensessie gestart', r.status_code == 302)
start = rijen('oefenen_start')
check('start vastgelegd met kaart, vorm en onderdelen',
      len(start) == 1 and start[0].kaart == 'Europa' and start[0].vorm == 'Meerkeuze'
      and start[0].onderdelen == 'Landen' and start[0].vragen == 41,
      [(s.kaart, s.vorm, s.onderdelen, s.vragen) for s in start])

from src import sessionManager  # noqa: E402
sessie = next(iter(sessionManager.sessions.values()))
with app.test_request_context('/', headers=telefoon):
    gebruik.legKlaar(sessie, {'totalGuesses': 50, 'time': 400, 'questionBreakdown': [
        {'name': 'Slovenie', 'tries': 3}, {'name': 'Verenigd Koninkrijk', 'tries': 1}]})
klaar = rijen('oefenen_klaar')
check('klaar vastgelegd met pogingen, duur en fouten',
      len(klaar) == 1 and klaar[0].pogingen == 50 and klaar[0].duur == 400
      and json.loads(klaar[0].fout) == {'Slovenie': 2}, [(k.pogingen, k.duur, k.fout) for k in klaar])

# --- Een gebeurtenis van vorige week, laat op de avond ------------------
with app.app_context():
    # 21:30 UTC is in de zomer 23:30 en in de winter 22:30 in Nederland.
    oud = datetime.utcnow().replace(hour=21, minute=30) - timedelta(days=6)
    db.session.add(Gebruik(tijd=oud, soort='bezoek', pagina='Startpagina', bezoeker='x', apparaat='computer'))
    db.session.add(Gebruik(tijd=oud - timedelta(days=60), soort='bezoek', pagina='Startpagina', bezoeker='y'))
    db.session.commit()

# --- Optellen ------------------------------------------------------------
with app.app_context():
    o = gebruik.overzicht('7')
    t = o['tegels']
    check('7 dagen: 7 dagen op de as', len(o['perDag']) == 7, len(o['perDag']))
    check('bezoekers geteld per dag', t['bezoekers'] == 2, t['bezoekers'])
    check('oude gebeurtenis valt buiten 7 dagen', t['weergaven'] == 3, t['weergaven'])
    check('sessies en afgemaakt', (t['gestart'], t['afgerond'], t['afgerondPct']) == (1, 1, 100),
          (t['gestart'], t['afgerond'], t['afgerondPct']))
    check('meteen goed = vragen / pogingen', t['treffers'] == 82, t['treffers'])
    check('mediane duur in minuten', t['duur'] == 6.7, t['duur'])
    check('Europa staat bij de kaarten', o['kaarten'][0]['naam'] == 'Europa')
    check('moeilijkste plek is Slovenie', o['moeilijkst'] and o['moeilijkst'][0]['plek'] == 'Slovenie', o['moeilijkst'])
    uur = gebruik._lokaal(oud).hour
    check('uur in Nederlandse tijd', o['perUur'][uur]['aantal'] >= 1 and uur in (22, 23), uur)
    check('telefoon en computer bij apparaten', {a['naam'] for a in o['apparaten']} == {'telefoon', 'computer'},
          o['apparaten'])
    check('alles: ook de oude gebeurtenis', gebruik.overzicht('alles')['tegels']['weergaven'] == 4)
    check('onbekende periode valt terug op 30 dagen', gebruik.overzicht('zomaar')['periode'] == '30')

# --- Grafiekmaten --------------------------------------------------------
g = gebruik.kolommen([{'label': str(i), 'a': i, 'b': 1} for i in range(24)], ['a', 'b'])
breedtes = [s['b'] for k in g['kolommen'] for s in k['stukken']]
check('kolommen hooguit 24 pixels breed', max(breedtes) <= 24, max(breedtes))
check('bovenste lijn boven de hoogste kolom', int(g['lijnen'][-1]['tekst']) >= 24, g['lijnen'][-1])
check('alleen het bovenste stuk is afgerond', all(not s['rond'] for k in g['kolommen'] for s in k['stukken'][:-1]))
leeg = gebruik.kolommen([{'label': 'a', 'x': 0}], ['x'])
check('lege grafiek geeft geen fout', leeg['kolommen'][0]['stukken'] == [])

# --- De pagina zelf ------------------------------------------------------
c.post('/host/login', data={'code': 'docent'})
r = c.get('/statistieken')
html = r.get_data(as_text=True)
check('met docentcode: pagina laadt', r.status_code == 200, r.status_code)
for stuk in ['Bezoekers per dag', 'Per uur van de dag', 'Week in uren', 'Moeilijkste plekken', 'Europa', 'Slovenie']:
    check(f'pagina toont "{stuk}"', stuk in html)
check('statistiekenpagina telt zichzelf niet mee', all(b.pagina != 'Statistieken' for b in rijen('bezoek')))
for periode in ['7', '30', '90', 'alles']:
    check(f'periode {periode} laadt', c.get('/statistieken?periode=' + periode).status_code == 200)
d = c.get('/statistieken.json').get_json()
check('json heeft het overzicht', 'overzicht' in d and d['overzicht']['tegels']['gestart'] == 1)
check('json alleen=nu is klein', 'overzicht' not in c.get('/statistieken.json?alleen=nu').get_json())

# --- Opslaan mag nooit de site breken -----------------------------------
with app.app_context():
    Gebruik.__table__.drop(db.engine)
r = c.get('/')
check('zonder tabel werkt de startpagina nog', r.status_code == 200, r.status_code)

print('\n' + ('ALLES GOED' if not fouten else 'MISLUKT: ' + ', '.join(fouten)))
sys.exit(1 if fouten else 0)
