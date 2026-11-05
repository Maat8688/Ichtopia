"""Test van /beheer: accounts hernoemen en verwijderen, woorden blokkeren.

Draaien vanuit de map `app`:

    python tests/test_beheer.py
"""
import sys
from datetime import datetime, timezone

from helpers import Checks, csrf, docentLogin, loadApp, register

app = loadApp()

from src.models import DuelMatch, Gebruik, GeblokkeerdWoord, User, db  # noqa: E402
from src.names import isAcceptable  # noqa: E402

check = Checks()


def token(client, pad='/beheer'):
    return csrf(client.get(pad).get_data(as_text=True))


def account(naam):
    with app.app_context():
        return User.query.filter_by(username=naam).first()


# Een paar accounts, een gespeeld duel en wat statistieken.
for naam in ['Floris', 'Sami', 'Joel']:
    register(app.test_client(), naam)
with app.app_context():
    sami, joel = account('Sami'), account('Joel')
    db.session.add(DuelMatch(map_name='Europa', questions=5, one_id=sami.id, two_id=joel.id,
                             one_score=900, two_score=400, one_rating_before=1000,
                             two_rating_before=1000, one_rating_after=1020, two_rating_after=980))
    db.session.add(Gebruik(tijd=datetime.now(timezone.utc).replace(tzinfo=None), soort='bezoek',
                           pagina='Startpagina'))
    db.session.commit()
    gebruikVoor = Gebruik.query.count()

# --- Afgeschermd ----------------------------------------------------------
gast = app.test_client()
r = gast.get('/beheer')
check('zonder docentcode: doorgestuurd naar de docentcode', r.status_code == 302 and '/host/login' in r.headers['Location'])
leerling = app.test_client()
register(leerling, 'Daan')
check('een gewoon account mag er ook niet in', leerling.get('/beheer').status_code == 302)
r = leerling.post(f'/beheer/account/{account("Floris").id}/verwijderen',
                  data={'csrfToken': token(leerling, '/account'), 'zeker': 'ja'})
check('en kan ook niet stiekem iets verwijderen', r.status_code == 302 and account('Floris') is not None)

d = app.test_client()
docentLogin(d, 'docent123')
pagina = d.get('/beheer').get_data(as_text=True)
check('met docentcode: de pagina laadt en toont de accounts',
      all(n in pagina for n in ['Floris', 'Sami', 'Joel']), pagina[:300])
check('zoeken werkt', 'Sami' in d.get('/beheer?zoek=sam').get_data(as_text=True)
      and 'Floris' not in d.get('/beheer?zoek=sam').get_data(as_text=True))

# --- Hernoemen ------------------------------------------------------------
fid = account('Floris').id
r = d.post(f'/beheer/account/{fid}/naam', data={'csrfToken': 'fout', 'naam': 'Flo'}, follow_redirects=True)
check('zonder geldig formulier verandert er niets', account('Floris') is not None)
r = d.post(f'/beheer/account/{fid}/naam', data={'csrfToken': token(d), 'naam': 'K4nk3r'}, follow_redirects=True)
check('een scheldwoord als nieuwe naam kan niet', account('Floris') is not None and 'kan niet' in r.get_data(as_text=True))
r = d.post(f'/beheer/account/{fid}/naam', data={'csrfToken': token(d), 'naam': 'sami'}, follow_redirects=True)
check('de naam van iemand anders kan niet', account('Floris') is not None)
r = d.post(f'/beheer/account/{fid}/naam', data={'csrfToken': token(d), 'naam': 'Flo'}, follow_redirects=True)
check('een goede nieuwe naam lukt', account('Flo') is not None and account('Floris') is None)
r = d.post(f'/beheer/account/{fid}/naam', data={'csrfToken': token(d), 'neutraal': '1'}, follow_redirects=True)
check('neutrale naam: Speler <nummer>', account(f'Speler {fid}') is not None, r.get_data(as_text=True)[-400:])

# --- Woorden blokkeren ----------------------------------------------------
check('voor het blokkeren mag "Skibidi" nog', isAcceptable('Skibidi'))
register(app.test_client(), 'SkibidiBoss')
r = d.post('/beheer/woord', data={'csrfToken': token(d), 'woord': 'skibidi'}, follow_redirects=True)
html = r.get_data(as_text=True)
check('woord toevoegen lukt', 'is geblokkeerd' in html)
check('en zegt welke accounts het al in hun naam hebben', 'SkibidiBoss' in html)
check('daarna mag "Sk1b.idi" niet meer', not isAcceptable('Sk1b.idi'))
nieuw = app.test_client()
t = csrf(nieuw.get('/registreren').get_data(as_text=True))
r = nieuw.post('/registreren', data={'csrfToken': t, 'username': 'skibidi toilet',
                                     'password': 'wachtwoord1', 'passwordRepeat': 'wachtwoord1'})
check('en kan niemand meer zo heten bij registreren', account('skibidi toilet') is None)
check('te korte woorden worden geweigerd',
      'minstens drie' in d.post('/beheer/woord', data={'csrfToken': token(d), 'woord': 'ab'},
                                follow_redirects=True).get_data(as_text=True))
with app.app_context():
    woord = GeblokkeerdWoord.query.filter_by(woord='skibidi').first()
d.post(f'/beheer/woord/{woord.id}/weg', data={'csrfToken': token(d)})
check('woord weghalen: dan mag het weer', isAcceptable('Skibidi'))

# --- Verwijderen ----------------------------------------------------------
sid = account('Sami').id
d.post(f'/beheer/account/{sid}/verwijderen', data={'csrfToken': token(d)})
check('zonder "zeker weten" wordt er niets verwijderd', account('Sami') is not None)
r = d.post(f'/beheer/account/{sid}/verwijderen', data={'csrfToken': token(d), 'zeker': 'ja'},
           follow_redirects=True)
check('met "zeker weten" is het account weg', account('Sami') is None)
with app.app_context():
    check('zijn duels zijn mee weg', DuelMatch.query.count() == 0)
    joel = User.query.filter_by(username='Joel').first()
    check('de tegenstander staat er nog', joel is not None)
    check('de statistieken zijn niet aangeraakt', Gebruik.query.count() >= gebruikVoor
          and Gebruik.query.filter_by(pagina='Startpagina').count() >= 1)

sys.exit(check.report())
