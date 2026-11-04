"""Test van de provincies op /statistieken.

Draaien vanuit de map `app`:

    python tests/test_locatie.py

Gebruikt een kleine nepdatabase in het formaat van DB-IP, met verzonnen
adressen. Nodig: pip install mmdb-writer (alleen voor deze test).
"""
import os
import sys
import tempfile

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HIER)
sys.path.insert(0, HIER)

from mmdb_writer import MMDBWriter  # noqa: E402
from netaddr import IPSet  # noqa: E402


def record(land, provincie=None):
    r = {'country': {'iso_code': land, 'names': {'en': land}}}
    if provincie:
        r['subdivisions'] = [{'names': {'en': provincie}}]
    return r


GEO = tempfile.mkstemp(suffix='.mmdb')[1]
schrijver = MMDBWriter(ip_version=4, database_type='DBIP-City-Lite')
schrijver.insert_network(IPSet(['31.151.10.0/24']), record('NL', 'Gelderland'))
schrijver.insert_network(IPSet(['84.80.20.0/24']), record('NL', 'Zeeland'))
schrijver.insert_network(IPSet(['62.45.0.0/24']), record('NL', 'North Holland'))
schrijver.insert_network(IPSet(['81.82.0.0/24']), record('BE', 'Flanders'))
schrijver.insert_network(IPSet(['145.97.0.0/24']), record('NL', 'Overijssel'))   # 'school'
schrijver.to_db_file(GEO)

os.environ.update(SECRET_KEY='test', KAHOOT_HOST_CODE='docent', GEO_DB=GEO,
                  SCHOOL_NETWERK='145.97.0.0/24',
                  DATABASE_URL='sqlite:///' + tempfile.mkstemp(suffix='.db')[1],
                  LOG_DIR=tempfile.mkdtemp())

import flask_sqlalchemy  # noqa: E402
flask_sqlalchemy.SQLAlchemy.create_all = lambda self, *a, **k: None   # zie dev.py

from sqlalchemy import inspect, text  # noqa: E402

from src import app, gebruik, locatie  # noqa: E402
from src.models import Gebruik, db  # noqa: E402

fouten = []


def check(naam, ok, extra=''):
    print(('OK   ' if ok else 'FOUT ') + naam + ('' if ok else ' :: ' + str(extra)[:300]))
    if not ok:
        fouten.append(naam)


# --- Een oude tabel zonder de nieuwe kolommen wordt bijgewerkt -----------
with app.app_context():
    with db.engine.begin() as v:
        v.execute(text('CREATE TABLE gebruik (id INTEGER PRIMARY KEY, tijd DATETIME NOT NULL, '
                       'soort VARCHAR(24) NOT NULL, pagina VARCHAR(40), bezoeker VARCHAR(16), '
                       'apparaat VARCHAR(12), kaart VARCHAR(40), vorm VARCHAR(20), onderdelen VARCHAR(200), '
                       'niveau VARCHAR(8), vragen INTEGER, pogingen INTEGER, duur INTEGER, spelers INTEGER, '
                       'fout TEXT)'))
    gebruik.zorgVoorKolommen()
    kolommen = {k['name'] for k in inspect(db.engine).get_columns('gebruik')}
    check('oude tabel krijgt land, provincie en school erbij', {'land', 'provincie', 'school'} <= kolommen, kolommen)
    gebruik.zorgVoorKolommen()
    check('nog een keer bijwerken kan geen kwaad', True)

# --- Opzoeken -------------------------------------------------------------
check('database gevonden', locatie.beschikbaar())
check('Gelderland', locatie.zoekOp('31.151.10.7') == ('NL', 'Gelderland'), locatie.zoekOp('31.151.10.7'))
check('Engelse naam wordt Nederlands', locatie.zoekOp('62.45.0.9') == ('NL', 'Noord-Holland'))
check('buitenland: alleen het land', locatie.zoekOp('81.82.0.1') == ('BE', None))
check('onbekend adres', locatie.zoekOp('8.8.8.8') == (None, None))
check('intern adres wordt niet opgezocht', locatie.zoekOp('192.168.1.5') == (None, None))
check('onzin', locatie.zoekOp('geen-ip') == (None, None) and locatie.zoekOp(None) == (None, None))
check('schoolnetwerk herkend', locatie.opSchool('145.97.0.20') is True and locatie.opSchool('31.151.10.7') is False)
check('alle provincienamen staan in de kaart', all(p['paden'] for p in locatie.provincieVormen()['provincies']))

# --- Bezoeken vanaf verschillende plekken --------------------------------
def bezoek(ip, n=1, pad='/'):
    for i in range(n):
        c = app.test_client()
        c.get(pad, environ_base={'REMOTE_ADDR': ip},
              headers={'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 test-{ip}-{i}',
                       'Accept-Language': 'nl-NL'})


bezoek('31.151.10.7', 7)       # 7 verschillende bezoekers uit Gelderland
bezoek('84.80.20.3', 2)        # 2 uit Zeeland: te weinig om precies te tonen
bezoek('62.45.0.9', 1)
bezoek('81.82.0.1', 1)          # België
bezoek('145.97.0.20', 3)        # op school (zou anders Overijssel zijn)
bezoek('8.8.8.8', 1)            # onbekend

with app.app_context():
    rijen = Gebruik.query.filter_by(soort='bezoek').all()
    check('elk bezoek opgeslagen', len(rijen) == 15, len(rijen))
    alles = ' '.join(f'{r.bezoeker} {r.land} {r.provincie} {r.pagina}' for r in rijen)
    check('geen IP-adres in de database', not any(ip in alles for ip in ['31.151', '84.80', '145.97', '8.8.8']))
    check('provincie opgeslagen', sum(1 for r in rijen if r.provincie == 'Gelderland') == 7)
    check('schoolbezoek gemarkeerd', sum(1 for r in rijen if r.school) == 3)

    p = gebruik.overzicht('30')['plekken']
    per = {r['naam']: r for r in p['provincies']}
    check('Gelderland: 7 bezoekers', per['Gelderland']['aantal'] == 7 and per['Gelderland']['tekst'] == '7')
    check('Zeeland: verborgen als < 5', per['Zeeland']['tekst'] == '< 5' and per['Zeeland']['stap'] == 1,
          per['Zeeland'])
    check('school telt niet als Overijssel', per['Overijssel']['aantal'] == 0, per['Overijssel'])
    check('schoolbezoeken apart geteld', p['school'] == 3 and p['schoolTekst'] == '< 5', (p['school'], p['schoolTekst']))
    check('buiten Nederland: België', p['landen'] and p['landen'][0]['naam'] == 'België', p['landen'])
    check('onbekend apart', p['onbekend'] == 1, p['onbekend'])
    check('drie provincies met bezoekers', p['metBezoekers'] == 3, p['metBezoekers'])
    check('voor het eerst gezien staat erbij', per['Gelderland']['eerste'] and per['Zeeland']['eerste'])
    check('in deze periode nieuw', per['Gelderland']['nieuw'])
    check('bij alles is niets nieuw', not any(r['nieuw'] for r in gebruik.overzicht('alles')['plekken']['provincies']))
    check('drukste provincie bovenaan', p['gerangschikt'][0]['naam'] == 'Gelderland')

# --- De pagina -------------------------------------------------------------
c = app.test_client()
c.post('/host/login', data={'code': 'docent'})
html = c.get('/statistieken').get_data(as_text=True)
check('pagina toont de provinciekaart', 'Waar komen bezoekers vandaan?' in html and 'class="prov s' in html)
check('aantal onder de 5 niet zichtbaar', 'Zeeland' in html and '&lt; 5 bezoekers' in html)
check('bronvermelding DB-IP', 'db-ip.com' in html)
d = c.get('/statistieken.json').get_json()
check('json zonder de kaartvormen', all('paden' not in r for r in d['overzicht']['plekken']['provincies']))

# --- Zonder database ------------------------------------------------------
locatie.GEO_DB = '/bestaat/niet.mmdb'
check('zonder database: niets bekend', locatie.zoekOp('31.151.10.7') == (None, None))
r = app.test_client().get('/', environ_base={'REMOTE_ADDR': '31.151.10.7'})
check('zonder database werkt de site gewoon', r.status_code == 200)
html = c.get('/statistieken').get_data(as_text=True)
check('pagina legt uit hoe je de database ophaalt', 'geo_bijwerken.py' in html)

print('\n' + ('ALLES GOED' if not fouten else 'MISLUKT: ' + ', '.join(fouten)))
sys.exit(1 if fouten else 0)
