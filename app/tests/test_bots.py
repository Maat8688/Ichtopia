"""Test van het herkennen van bots en de knop op /statistieken.

Draaien vanuit de map `app`:

    python tests/test_bots.py
"""
import os
import sys
import tempfile
from datetime import timedelta

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HIER)
sys.path.insert(0, HIER)
os.environ.update(SECRET_KEY='test', KAHOOT_HOST_CODE='docent', SCHOOL_NETWERK='145.97.0.0/24',
                  GEO_DB='/bestaat/niet.mmdb',
                  DATABASE_URL='sqlite:///' + tempfile.mkstemp(suffix='.db')[1], LOG_DIR=tempfile.mkdtemp())

from helpers import docentLogin, loadApp  # noqa: E402
loadApp()   # tijdelijke sqlite-database met alle tabellen

from src import app, gebruik  # noqa: E402
from src.models import Gebruik, db  # noqa: E402

with app.app_context():
    Gebruik.__table__.create(db.engine, checkfirst=True)

fouten = []


def check(naam, ok, extra=''):
    print(('OK   ' if ok else 'FOUT ') + naam + ('' if ok else ' :: ' + str(extra)[:300]))
    if not ok:
        fouten.append(naam)


CHROME = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
IPHONE = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 '
          '(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1')

# --- Herkennen aan de browsernaam en de taal -----------------------------
gevallen = [
    ('mens: Chrome', CHROME, 'nl-NL', None),
    ('mens: iPhone', IPHONE, 'nl-NL,nl;q=0.9', None),
    ('mens: telefoon van het merk Cubot', 'Mozilla/5.0 (Linux; Android 13; CUBOT KINGKONG 9) Chrome/119 Mobile', 'nl', None),
    ('Googlebot', 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)', None, 'zoekmachine'),
    ('GPTBot', 'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2)', None, 'AI-crawler'),
    ('WhatsApp-voorbeeld', 'WhatsApp/2.23.20.0 A', None, 'linkvoorbeeld'),
    ('curl', 'curl/8.4.0', None, 'script'),
    ('Python', 'python-requests/2.31.0', None, 'script'),
    ('headless', CHROME.replace('Chrome/', 'HeadlessChrome/'), 'en-US', 'headless browser'),
    ('onbekende bot', 'Mozilla/5.0 (compatible; NieuweBot/1.0)', 'en', 'andere bot'),
    ('geen browsernaam', '', None, 'geen browsernaam'),
    ('browser zonder taal', CHROME, None, 'geen taal'),
]
for naam, browser, taal, verwacht in gevallen:
    uit = gebruik.botReden(browser, taal)
    check(naam, uit == verwacht, uit)

# --- Opgeslagen bij een bezoek ------------------------------------------
c = app.test_client()
mens = {'User-Agent': CHROME, 'Accept-Language': 'nl-NL'}
c.get('/', headers=mens)
c.get('/', headers={'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1)'})
c.get('/', headers={'User-Agent': 'curl/8.4.0'})
c.post('/', data={'KaartInput': 'Europa', 'mode': 'MultipleChoise', 'questions': ['Landen']},
       headers={'User-Agent': 'python-requests/2.31.0'})
with app.app_context():
    redenen = sorted(str(r.bot) for r in Gebruik.query.filter_by(soort='bezoek').all())
    check('reden bij het bezoek opgeslagen', redenen == ['None', 'script', 'zoekmachine'], redenen)
    start = Gebruik.query.filter_by(soort='oefenen_start').all()
    check('ook een oefensessie van een script telt als bot', start and start[0].bot == 'script',
          [s.bot for s in start])

# --- Afmaken erft het oordeel van het begin ------------------------------
from src import sessionManager  # noqa: E402
sessie = next(iter(sessionManager.sessions.values()))
with app.test_request_context('/', headers=mens):          # via de websocket: wel een browser
    gebruik.legKlaar(sessie, {'totalGuesses': 41, 'time': 60, 'questionBreakdown': []})
with app.app_context():
    klaar = Gebruik.query.filter_by(soort='oefenen_klaar').first()
    check('afmaken neemt het oordeel van het begin over', klaar.bot == 'script', klaar.bot)

c.post('/', data={'KaartInput': 'Europa', 'mode': 'MultipleChoise', 'questions': ['Landen']}, headers=mens)
sessie2 = [s for s in sessionManager.sessions.values() if s is not sessie][0]
with app.test_request_context('/', headers={'User-Agent': CHROME}):   # websocket zonder taal
    gebruik.legKlaar(sessie2, {'totalGuesses': 41, 'time': 60, 'questionBreakdown': []})
with app.app_context():
    klaar2 = Gebruik.query.filter_by(soort='oefenen_klaar').order_by(Gebruik.id.desc()).first()
    check('websocket zonder taal maakt een mens geen bot', klaar2.bot is None, klaar2.bot)

# --- Te snel -------------------------------------------------------------
with app.app_context():
    nu = gebruik._nuUtc().replace(second=1)
    for i in range(50):                       # 50 pagina's in een minuut: geen mens
        db.session.add(Gebruik(tijd=nu - timedelta(hours=2) + timedelta(seconds=i), soort='bezoek',
                               pagina='Startpagina', bezoeker='snelsnel', apparaat='computer'))
    for i in range(50):                       # zelfde tempo, maar op school: telt niet als bot
        db.session.add(Gebruik(tijd=nu - timedelta(hours=3) + timedelta(seconds=i), soort='bezoek',
                               pagina='Startpagina', bezoeker='klaslokaal', apparaat='computer', school=True))
    for i in range(10):                       # rustig: een mens
        db.session.add(Gebruik(tijd=nu - timedelta(hours=4, minutes=i * 3), soort='bezoek',
                               pagina='Oefenen', bezoeker='rustig', apparaat='computer'))
    db.session.commit()

    weg = gebruik.overzicht('7', bots='weg')
    mee = gebruik.overzicht('7', bots='mee')
    b = weg['bots']
    redenen = {r['naam']: r['aantal'] for r in b['redenen']}
    check('50 per minuut is te snel', redenen.get('te snel') == 50, redenen)
    check('op school is 50 per minuut geen bot', 'klaslokaal' not in str(b) and redenen.get('te snel') == 50)
    check('weglaten: alleen mensen geteld', weg['tegels']['weergaven'] == 1 + 50 + 10, weg['tegels']['weergaven'])
    check('meenemen: alles geteld', mee['tegels']['weergaven'] == 3 + 50 + 50 + 10, mee['tegels']['weergaven'])
    check('weglaten: oefensessie van het script telt niet', weg['tegels']['gestart'] == 1, weg['tegels']['gestart'])
    check('meenemen: wel', mee['tegels']['gestart'] == 2, mee['tegels']['gestart'])
    check('percentage bots', b['weergavenPct'] == round(100 * 52 / 113), b['weergavenPct'])
    # Over de hele week opgeteld: 'een paar uur geleden' kan na middernacht gisteren zijn.
    som = lambda o, k: sum(d[k] for d in o['perDag'])
    check('per dag: mensen en bots apart', (som(mee, 'mensen'), som(mee, 'bots')) == (3, 3),
          (som(mee, 'mensen'), som(mee, 'bots')))
    check('bij weglaten: bezoekers = mensen', som(weg, 'bezoekers') == som(weg, 'mensen'))
    check('bij meenemen: bezoekers = mensen + bots',
          som(mee, 'bezoekers') == som(mee, 'mensen') + som(mee, 'bots'))
    check('modus staat erbij', (weg['bots']['modus'], mee['bots']['modus']) == ('weg', 'mee'))

# --- De knop -------------------------------------------------------------
docentLogin(c, 'docent')
html = c.get('/statistieken?periode=7').get_data(as_text=True)
check('standaard: bots weggelaten', 'Weggelaten: 52' in html, html[html.find('bot-regel'):][:200])
check('knop meenemen verwijst naar dezelfde periode', 'periode=7&amp;bots=mee' in html or 'bots=mee&amp;periode=7' in html)
html = c.get('/statistieken?periode=7&bots=mee').get_data(as_text=True)
check('meenemen: grafiek met mensen en bots', 'Inclusief 52' in html and '<i class="r2"></i>bots' in html)
check('periodeknoppen houden bots=mee vast', 'periode=30&amp;bots=mee' in html or 'bots=mee&amp;periode=30' in html)
check('uitleg over bots op de pagina', 'Hoe we een bot herkennen' in html)
check('onzin in bots= valt terug op weglaten', 'Weggelaten' in c.get('/statistieken?bots=hallo').get_data(as_text=True))
check('json volgt de knop', c.get('/statistieken.json?periode=7&bots=mee').get_json()['overzicht']['bots']['modus'] == 'mee')

print('\n' + ('ALLES GOED' if not fouten else 'MISLUKT: ' + ', '.join(fouten)))
sys.exit(1 if fouten else 0)
