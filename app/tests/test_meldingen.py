"""Test van de meldingen: "Klopt dit niet?", het formulier, en /beheer/meldingen.

Draaien vanuit de map `app`:

    python tests/test_meldingen.py
"""
import re
import sys

from helpers import Checks, csrf, docentLogin, loadApp

app = loadApp()

import importlib  # noqa: E402
from src import sessionManager  # noqa: E402
meldingModule = importlib.import_module('src.meldingen')
from src.models import Melding, db  # noqa: E402

check = Checks()
FETCH = {'X-Requested-With': 'fetch'}


def meldingen(**filter_):
    with app.app_context():
        return Melding.query.filter_by(**filter_).order_by(Melding.id).all()


def token(client, pad='/melden'):
    return csrf(client.get(pad).get_data(as_text=True))


def nieuweSessie(client, soort='oefenen'):
    data = {'KaartInput': 'Europa', 'mode': 'MultipleChoise', 'questions': ['Landen']}
    if soort == 'toets':
        data.update(soort='toets', toetsVragen='10')
    r = client.post('/', data=data)
    sessieToken = re.search(r'sessionToken=([^&]+)', r.headers['Location']).group(1)
    from urllib.parse import unquote
    sessieToken = unquote(sessieToken)
    return sessieToken, sessionManager.findSession(sessieToken)


# --- Overal een link naar het formulier -----------------------------------
c = app.test_client()
start = c.get('/').get_data(as_text=True)
check('de startpagina linkt naar het meldformulier', '/melden?van=/' in start)
check('het formulier laadt', c.get('/melden?van=/ranglijst').status_code == 200)

# --- Het formulier --------------------------------------------------------
r = c.post('/melden', data={'csrfToken': 'fout', 'soort': 'kapot', 'tekst': 'De knop doet niets'})
check('zonder geldig formulier: niets opgeslagen', not meldingen())
r = c.post('/melden', data={'csrfToken': token(c), 'soort': 'kapot', 'tekst': 'x'}, follow_redirects=True)
check('een lege melding wordt geweigerd', not meldingen() and 'Schrijf even op' in r.get_data(as_text=True))
r = c.post('/melden', data={'csrfToken': token(c), 'soort': 'raar', 'tekst': 'hallo daar'})
check('een onbekende soort wordt geweigerd', not meldingen())
r = c.post('/melden', follow_redirects=True, data={
    'csrfToken': token(c), 'soort': 'idee', 'tekst': 'Een kaart van Azië graag!\x07',
    'pagina': '/learn?sessionToken=geheim'})
m = meldingen()
check('een idee wordt opgeslagen', len(m) == 1 and m[0].soort == 'idee', m)
check('en je komt op de bedankpagina', 'Bedankt' in r.get_data(as_text=True))
check('onzichtbare tekens worden eruit gehaald', m and m[0].tekst == 'Een kaart van Azië graag!')
check('van de pagina wordt alleen het pad bewaard, zonder sessietoken', m and m[0].pagina == '/learn')
c.post('/melden', data={'csrfToken': token(c), 'soort': 'kapot', 'tekst': 'a' * 2000})
check('te lange tekst wordt op 500 tekens afgekapt', len(meldingen(soort='kapot')[0].tekst) == 500)
c.post('/melden', data={'csrfToken': token(c), 'soort': 'kapot', 'tekst': 'iets', 'pagina': 'https://evil.example/'})
check('een pagina buiten de site wordt niet bewaard', meldingen(soort='kapot')[-1].pagina is None)
with app.app_context():
    kolommen = {k['name'] for k in db.inspect(db.engine).get_columns('melding')}
check('er is geen kolom voor IP-adres of account', not ({'ip', 'user_id', 'naam'} & kolommen), kolommen)

# --- "Klopt dit niet?" tijdens het oefenen --------------------------------
leerling = app.test_client()
sessieToken, sessie = nieuweSessie(leerling)
r = leerling.post('/melden', headers=FETCH, data={
    'csrfToken': token(leerling), 'soort': 'kaart', 'reden': 'antwoord', 'sessionToken': sessieToken})
check('voor het eerste antwoord valt er nog niets te melden', r.status_code == 400 and not r.get_json()['ok'])

vraag = sessie.currentQuestion
sessie.awnserQuestion('Atlantis', False)          # een fout antwoord
r = leerling.post('/melden', headers=FETCH, data={
    'csrfToken': token(leerling), 'soort': 'kaart', 'reden': 'spelling',
    'sessionToken': sessieToken, 'tekst': 'Staat er niet zo in mijn atlas'})
check('kaartmelding geeft een JSON-antwoord', r.status_code == 200 and r.get_json()['ok'], r.get_data(as_text=True))
km = meldingen(soort='kaart')
check('de server vult kaart, vraag en antwoord zelf in',
      len(km) == 1 and km[0].kaart == 'Europa' and km[0].vraag == vraag.displayName
      and km[0].antwoord == 'Atlantis' and km[0].reden == 'spelling', km and vars(km[0]))
leerling.post('/melden', headers=FETCH, data={
    'csrfToken': token(leerling), 'soort': 'kaart', 'reden': 'plek', 'sessionToken': sessieToken})
check('dezelfde vraag twee keer melden telt een keer', len(meldingen(soort='kaart')) == 1)
r = leerling.post('/melden', headers=FETCH, data={
    'csrfToken': token(leerling), 'soort': 'kaart', 'reden': 'onzin', 'sessionToken': sessieToken})
check('een onbekende reden wordt geweigerd', r.status_code == 400)
r = leerling.post('/melden', headers=FETCH, data={
    'csrfToken': token(leerling), 'soort': 'kaart', 'reden': 'plek', 'sessionToken': 'verlopen'})
check('met een verlopen sessie kan het niet', r.status_code == 400)

# --- In de uitslag van een toets ------------------------------------------
toetsToken, toets = nieuweSessie(leerling, 'toets')
toets.beantwoordToets('Atlantis', False)
gevraagd = toets.toetsAntwoorden[0]['vraag']
r = leerling.post('/melden', headers=FETCH, data={
    'csrfToken': token(leerling), 'soort': 'kaart', 'reden': 'antwoord',
    'sessionToken': toetsToken, 'vraag': gevraagd})
check('een vraag uit de toets melden lukt', r.status_code == 200 and r.get_json()['ok'])
check('met het antwoord dat de leerling gaf', meldingen(vraag=gevraagd)[-1].antwoord == 'Atlantis')
r = leerling.post('/melden', headers=FETCH, data={
    'csrfToken': token(leerling), 'soort': 'kaart', 'reden': 'antwoord',
    'sessionToken': toetsToken, 'vraag': 'Iets wat er niet in zat'})
check('een vraag die niet in de toets zat wordt geweigerd', r.status_code == 400)

# --- De oefenpagina heeft het knopje --------------------------------------
pagina = leerling.get('/learn?sessionToken=' + sessieToken).get_data(as_text=True)
check('de oefenpagina heeft het meldpaneel', 'id="meldPaneel"' in pagina and 'Klopt dit niet?' in pagina)

# --- Rem tegen volspammen -------------------------------------------------
spammer = app.test_client()
t = token(spammer)
statussen = [spammer.post('/melden', headers=FETCH, data={'csrfToken': t, 'soort': 'idee',
                                                         'tekst': f'spam nummer {i}'}).status_code
             for i in range(40)]
check('na 30 meldingen per 10 minuten is het op', statussen.count(200) <= 30 and statussen[-1] == 429,
      statussen[-12:])
meldingModule.meldLimiter._attempts.clear()   # voor de rest van de test

# --- /beheer/meldingen ----------------------------------------------------
check('zonder docentcode kom je er niet in', app.test_client().get('/beheer/meldingen').status_code == 302)
d = app.test_client()
docentLogin(d, 'docent123')
html = d.get('/beheer/meldingen').get_data(as_text=True)
check('met docentcode zie je de meldingen', 'Een kaart van Azië graag!' in html and vraag.displayName in html)
check('kaartvragen staan opgeteld bovenaan', 'Kaartvragen die gemeld zijn' in html)
check('de beheerpagina noemt het aantal open meldingen', 'melding' in d.get('/beheer').get_data(as_text=True).lower()
      and 'meldingen van bezoekers open' in d.get('/beheer').get_data(as_text=True))

idee = meldingen(soort='idee')[0]
d.post(f'/beheer/melding/{idee.id}/afgehandeld', data={'csrfToken': token(d, '/beheer/meldingen')})
check('afhandelen werkt', meldingen(id=idee.id)[0].afgehandeld)
check('afgehandeld staat niet meer bij open',
      'Een kaart van Azië graag!' not in d.get('/beheer/meldingen').get_data(as_text=True))
check('maar wel bij afgehandeld',
      'Een kaart van Azië graag!' in d.get('/beheer/meldingen?toon=afgehandeld').get_data(as_text=True))
d.post(f'/beheer/melding/{idee.id}/afgehandeld', data={'csrfToken': token(d, '/beheer/meldingen')})
check('en weer open zetten kan ook', not meldingen(id=idee.id)[0].afgehandeld)

d.post('/beheer/meldingen/vraag-afgehandeld', data={'csrfToken': token(d, '/beheer/meldingen'),
                                                    'kaart': 'Europa', 'vraag': vraag.displayName})
check('alle meldingen over een vraag in een keer afhandelen', all(m.afgehandeld for m in meldingen(vraag=vraag.displayName)))

d.post(f'/beheer/melding/{idee.id}/verwijderen', data={'csrfToken': 'fout'})
check('verwijderen zonder geldig formulier doet niets', meldingen(id=idee.id))
d.post(f'/beheer/melding/{idee.id}/verwijderen', data={'csrfToken': token(d, '/beheer/meldingen')})
check('verwijderen werkt', not meldingen(id=idee.id))
r = app.test_client().post(f'/beheer/melding/{km[0].id}/verwijderen', data={'csrfToken': 'x'})
check('een leerling kan niets verwijderen', meldingen(id=km[0].id))

check('de privacypagina noemt de meldingen', 'Als je iets meldt' in c.get('/privacy').get_data(as_text=True))

sys.exit(check.report())
