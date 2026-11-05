"""Test van de privacypagina, je eigen account verwijderen, en dat de site
niets bij andere partijen ophaalt.

Draaien vanuit de map `app`:

    python tests/test_privacy.py
"""
import glob
import re
import sys

from helpers import Checks, csrf, loadApp, register

app = loadApp()

from src.models import DuelMatch, User, db  # noqa: E402

check = Checks()

gast = app.test_client()
r = gast.get('/privacy')
check('privacypagina is voor iedereen', r.status_code == 200)
tekst = r.get_data(as_text=True)
check('noemt dat er geen e-mail wordt bewaard', 'Geen e-mail' in tekst)
check('noemt het logbestand met IP-adressen', 'logbestand' in tekst and 'IP-adres' in tekst)
check('de startpagina linkt naar de privacypagina', 'href="/privacy"' in gast.get('/').get_data(as_text=True))

# --- Niets van andere partijen --------------------------------------------
# Elke externe bron stuurt het IP-adres van een leerling naar iemand anders.
extern = []
for pad in glob.glob('templates/**/*.html', recursive=True) + glob.glob('static/css/*.css'):
    inhoud = open(pad, encoding='utf-8').read()
    for url in re.findall(r'''(?:src|href)=["'](https?://[^"']+)|@import\s+url\(["']?(https?://[^"')]+)|url\(["']?(https?://[^"')]+)''', inhoud):
        url = next(u for u in url if u)
        if 'db-ip.com' in url:      # een gewone link in de bronvermelding, geen bron die laadt
            continue
        extern.append(f'{pad}: {url}')
check('geen lettertypes of scripts van andere sites', not extern, extern[:5])
check('het lettertype staat er zelf', gast.get('/static/fonts/lexend-latin.woff2').status_code == 200)
check('socket.io staat er zelf', gast.get('/static/js/vendor/socket.io-4.0.0.min.js').status_code == 200)

# --- Je eigen account verwijderen -----------------------------------------
floris, sami = app.test_client(), app.test_client()
register(floris, 'Floris')
register(sami, 'Sami')
with app.app_context():
    f = User.query.filter_by(username='Floris').first()
    s = User.query.filter_by(username='Sami').first()
    db.session.add(DuelMatch(map_name='Europa', questions=5, one_id=f.id, two_id=s.id,
                             one_score=1, two_score=0, one_rating_before=1000, two_rating_before=1000,
                             one_rating_after=1010, two_rating_after=990))
    db.session.commit()

pagina = floris.get('/account').get_data(as_text=True)
check('de knop staat op Mijn account', 'Account verwijderen' in pagina)
r = floris.post('/account/verwijderen', data={'csrfToken': csrf(pagina), 'password': 'fout'},
                follow_redirects=True)
with app.app_context():
    check('met een fout wachtwoord gebeurt er niets', User.query.filter_by(username='Floris').first() is not None)
r = floris.post('/account/verwijderen', data={'csrfToken': 'fout', 'password': 'wachtwoord1'})
with app.app_context():
    check('zonder geldig formulier ook niet', User.query.filter_by(username='Floris').first() is not None)
r = floris.post('/account/verwijderen', follow_redirects=True,
                data={'csrfToken': csrf(floris.get('/account').get_data(as_text=True)), 'password': 'wachtwoord1'})
with app.app_context():
    check('met het goede wachtwoord is het account weg', User.query.filter_by(username='Floris').first() is None)
    check('zijn duels zijn mee weg', DuelMatch.query.count() == 0)
    check('de tegenstander blijft', User.query.filter_by(username='Sami').first() is not None)
check('en je bent uitgelogd', floris.get('/account').status_code == 302)
check('de naam is weer vrij', register(app.test_client(), 'Floris').status_code == 200)

sys.exit(check.report())
