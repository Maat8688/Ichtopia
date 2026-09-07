"""Test van punten, levels, elo en de ranglijst - inclusief een heel duel.

Draaien vanuit de map `app`:

    python tests/test_ranking.py

Het duel wordt echt gespeeld via de socketverbinding, met twee testclients.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import Checks, csrf, loadApp, register   # noqa: E402

app = loadApp()

from src import socketio                              # noqa: E402
from src import duel_routes                           # noqa: E402
from src.duel_routes import duelManager               # noqa: E402
from src import sessionManager                        # noqa: E402
from src.models import DuelMatch, User, db            # noqa: E402
from src.progress import (levelForXp, levelProgress, newRating, practiceXp,
                          xpForLevel)                 # noqa: E402

# Anders duurt de test net zo lang als een echt duel.
duel_routes.REVEAL_SECONDS = 0.2
duel_routes.START_COUNTDOWN = 0.2

check = Checks()

# ----------------------------------------------------------------------
# Rekenwerk
# ----------------------------------------------------------------------
check('level 1 begint op 0 XP', xpForLevel(1) == 0)
check('level loopt op', xpForLevel(2) == 50 and xpForLevel(5) == 500)
check('level bij 200 XP is 3', levelForXp(200) == 3)
check('voortgang klopt', levelProgress(200)['toNext'] == 100)
check('XP voor oefenen schaalt met de kaart',
      practiceXp(41, 41) > practiceXp(20, 20) > 0)
check('slordig oefenen levert minder op', practiceXp(41, 100) < practiceXp(41, 41))
check('winnen levert elo op', newRating(1000, 1000, 1, 0) > 1000)
check('verliezen kost elo', newRating(1000, 1000, 0, 0) < 1000)
check('winnen van een sterkere levert meer op',
      newRating(1000, 1400, 1, 20) - 1000 > newRating(1000, 800, 1, 20) - 1000)
check('elo zakt nooit onder de bodem', newRating(100, 2000, 0, 50) >= 100)

# ----------------------------------------------------------------------
# XP bijschrijven en de dagrem
# ----------------------------------------------------------------------
clientA = app.test_client()
clientB = app.test_client()
register(clientA, 'Floris', 'a@example.com')
register(clientB, 'Sami', 'b@example.com')

with app.app_context():
    user = User.query.filter_by(email='a@example.com').first()
    check('nieuw account begint op 0 XP en 1000 elo', user.xp == 0 and user.rating == 1000)
    check('nieuw account is level 1', user.level == 1)
    added = user.addXp(120, cap=600)
    check('XP bijschrijven', added == 120 and user.xp == 120 and user.level == 2)
    added = user.addXp(1000, cap=600)
    check('dagrem kapt af', added == 480 and user.xp == 600)
    added = user.addXp(50, cap=600)
    check('daarna komt er niets meer bij', added == 0 and user.xp == 600)
    db.session.commit()

# ----------------------------------------------------------------------
# XP voor een afgeronde oefensessie
# ----------------------------------------------------------------------
clientC = app.test_client()
register(clientC, 'Joel', 'c@example.com')

response = clientC.post('/', data={'KaartInput': 'Europa', 'mode': 'FillInTheBlank',
                                   'questions': ['Landen']})
token = response.headers['Location'].split('sessionToken=')[-1]
from urllib.parse import unquote                       # noqa: E402
token = unquote(token)
socketC = socketio.test_client(app, flask_test_client=clientC)
session = sessionManager.getSession(token)
xpMelding = None
for _ in range(len(session.questions) * 3):
    if session.finished:
        break
    socketC.emit('answerQuestion', {'awnser': session.currentQuestion.displayName,
                                    'hashed': False, 'sessionToken': token})
    for message in socketC.get_received():
        if message['name'] == 'finished':
            xpMelding = message['args'][0].get('xp')
check('oefensessie is afgerond', session.finished)
check('afgeronde oefensessie levert XP op', xpMelding and xpMelding['earned'] > 0, xpMelding)
check('de sessie geeft je level terug', xpMelding and xpMelding['level'] >= 2, xpMelding)
with app.app_context():
    joel = User.query.filter_by(email='c@example.com').first()
    check('XP staat in de database', joel.xp == xpMelding['earned'], joel.xp)
socketC.disconnect()

# ----------------------------------------------------------------------
# Ranglijst
# ----------------------------------------------------------------------
page = clientA.get('/ranglijst').get_data(as_text=True)
check('ranglijst toont de XP-lijst', 'Floris' in page and '600 XP' in page)
check('ranglijst toont je eigen plaats', 'Jij staat op plaats 1' in page)
page = clientA.get('/ranglijst?lijst=elo').get_data(as_text=True)
check('elo-lijst is nog leeg', 'nog geen enkel duel' in page)
check('ranglijst mag ook zonder inloggen',
      app.test_client().get('/ranglijst').status_code == 200)

# De ingang naar een duel moet op de startpagina staan, ook zonder inloggen:
# een linkje in de kopbalk alleen is op een telefoon niet te vinden.
startIngelogd = clientA.get('/').get_data(as_text=True)
startUitgelogd = app.test_client().get('/').get_data(as_text=True)
check('startpagina wijst de weg naar een duel', 'href="/duel"' in startIngelogd)
check('die rij staat er ook als je niet ingelogd bent', 'href="/duel"' in startUitgelogd)
check('startpagina wijst de weg naar de ranglijst', 'href="/ranglijst"' in startUitgelogd)

# ----------------------------------------------------------------------
# Een heel duel spelen
# ----------------------------------------------------------------------
response = clientA.post('/duel/nieuw', data={
    'KaartInput': 'Europa', 'mode': 'MultipleChoise', 'questions': ['Landen'],
    'questionCount': 3, 'seconds': 30, 'open': '1',
})
check('duel aanmaken stuurt door naar het duel', response.status_code == 302, response.status_code)
code = response.headers['Location'].rstrip('/').split('/')[-1]
duel = duelManager.getDuel(code)
check('duel staat klaar', duel is not None and len(duel.questions) == 3)

page = clientB.get('/duel').get_data(as_text=True)
check('duel staat in de lijst met openstaande duels', 'Floris' in page and 'Spelen' in page)
duelPagina = clientA.get('/duel/' + code)
check('duelpagina laadt', duelPagina.status_code == 200)
check('meerkeuzeduel toont de kaart (er is geen digibord om naar te kijken)',
      '<svg id="map"' in duelPagina.get_data(as_text=True))

# Aanwijzen op de kaart heeft de hele kaart in de pagina nodig.
klikDuel = clientB.post('/duel/nieuw', data={
    'KaartInput': 'Nederland', 'mode': 'ClickTheCountry', 'questions': ['Provincies'],
    'questionCount': 3, 'seconds': 30,
})
klikCode = klikDuel.headers['Location'].rstrip('/').split('/')[-1]
klikPagina = clientB.get('/duel/' + klikCode)
check('duel met aanwijzen toont de kaart',
      klikPagina.status_code == 200 and '<svg id="map"' in klikPagina.get_data(as_text=True))

socketA = socketio.test_client(app, flask_test_client=clientA)
socketB = socketio.test_client(app, flask_test_client=clientB)
socketA.emit('duelJoin', {'code': code})
socketB.emit('duelJoin', {'code': code})


def received(client, event):
    """Alle berichten van dit type die tot nu toe binnenkwamen."""
    return [m['args'][0] if m['args'] else {}
            for m in client.get_received() if m['name'] == event]


def waitFor(client, event, timeout=8):
    """Wacht tot dit bericht binnenkomt; verzamel de rest onderweg."""
    end = time.time() + timeout
    while time.time() < end:
        for message in client.get_received():
            if message['name'] == event:
                return message['args'][0] if message['args'] else {}
        time.sleep(0.05)
    return None


check('het duel begint zodra allebei binnen zijn',
      waitFor(socketA, 'duelStarting') is not None)

goedeAntwoorden = 0
for i in range(3):
    question = waitFor(socketA, 'duelQuestion')
    waitFor(socketB, 'duelQuestion', timeout=2)
    if question is None:
        check(f'vraag {i + 1} komt binnen', False, 'geen vraag ontvangen')
        break
    # Floris antwoordt goed, Sami fout: de uitslag mag niet van toeval afhangen.
    if i == 0:
        check('meerkeuzevraag vertelt welk gebied gevraagd wordt',
              bool(question.get('mapId')), question)
        check('meerkeuzevraag geeft de categorie mee voor het oplichten',
              bool(question.get('category')), question)
    juist = duel.currentQuestion.displayName
    fout = next((o for o in question['options'] if o != juist), juist)
    socketA.emit('duelAnswer', {'code': code, 'answer': juist, 'hashed': False})
    socketB.emit('duelAnswer', {'code': code, 'answer': fout, 'hashed': False})
    reveal = waitFor(socketA, 'duelReveal')
    if reveal and reveal['correct']:
        goedeAntwoorden += 1
    if i == 0:
        check('de uitslag wijst het goede gebied aan',
              bool(reveal and reveal.get('mapId')), reveal)

check('alle drie de vragen goed gerekend', goedeAntwoorden == 3, goedeAntwoorden)

eindeA = waitFor(socketA, 'duelFinished')
eindeB = waitFor(socketB, 'duelFinished')
check('winnaar krijgt de uitslag', eindeA is not None and eindeA['outcome'] == 'gewonnen', eindeA)
check('verliezer krijgt de uitslag', eindeB is not None and eindeB['outcome'] == 'verloren', eindeB)
check('winnaar wint elo', eindeA and eindeA['ratingChange'] > 0, eindeA)
check('verliezer verliest elo', eindeB and eindeB['ratingChange'] < 0, eindeB)
check('elo verschuift even veel als hij optelt',
      eindeA and eindeB and eindeA['ratingChange'] == -eindeB['ratingChange'])
check('de verliezer houdt er ook XP aan over', eindeB and eindeB['xpEarned'] > 0, eindeB)

with app.app_context():
    winnaar = User.query.filter_by(email='a@example.com').first()
    verliezer = User.query.filter_by(email='b@example.com').first()
    match = DuelMatch.query.first()
    check('duel is opgeslagen', match is not None and match.rated is True)
    check('score staat erbij', match and match.one_score > match.two_score)
    check('elo van de winnaar staat in de database', winnaar.rating > 1000, winnaar.rating)
    check('elo van de verliezer staat in de database', verliezer.rating < 1000, verliezer.rating)
    check('gewonnen en verloren zijn geteld',
          winnaar.duels_won == 1 and verliezer.duels_lost == 1)
    check('uitslag vanuit de winnaar gezien', match.resultFor(winnaar.id) == 'gewonnen')
    check('uitslag vanuit de verliezer gezien', match.resultFor(verliezer.id) == 'verloren')

page = clientA.get('/ranglijst?lijst=elo').get_data(as_text=True)
check('elo-lijst toont beide spelers', 'Floris' in page and 'Sami' in page)
page = clientA.get('/account').get_data(as_text=True)
check('accountpagina toont het duel', 'Laatste duels' in page and 'gewonnen' in page)
check('accountpagina toont je level', 'Level' in page)

# Een derde speler kan er niet meer bij.
check('vol duel weigert een derde speler', clientC.get('/duel/' + code).status_code == 403)
check('onbekende code geeft een nette pagina',
      clientC.get('/duel/ZZZZZ').status_code == 404)
check('duel vereist inloggen',
      app.test_client().get('/duel').status_code == 302)

socketA.disconnect()
socketB.disconnect()

# ----------------------------------------------------------------------
# De rem op eenzijdig voeren
# ----------------------------------------------------------------------
from src.duel_routes import RATED_WINS_PER_PAIR_PER_DAY, isRated   # noqa: E402


def bewaarDuel(winnaar, verliezer, rated=True):
    db.session.add(DuelMatch(
        map_name='Europa', questions=3, rated=rated,
        one_id=winnaar.id, two_id=verliezer.id, one_score=1000, two_score=0,
        one_rating_before=winnaar.rating, two_rating_before=verliezer.rating,
        one_rating_after=winnaar.rating, two_rating_after=verliezer.rating,
    ))
    db.session.commit()


with app.app_context():
    een = User.query.filter_by(email='a@example.com').first()
    twee = User.query.filter_by(email='b@example.com').first()
    drie = User.query.filter_by(email='c@example.com').first()

    # Het duel hierboven telde al als een overwinning van 'een' op 'twee'.
    for _ in range(RATED_WINS_PER_PAIR_PER_DAY - 1):
        bewaarDuel(een, twee)
    check('winnen telt tot de grens', isRated(een, twee, 1.0) is False,
          'na de grens moet het stoppen')
    # De andere kant op is een losse teller: teruggewonnen duels blijven tellen.
    check('om de beurt winnen blijft altijd tellen', isRated(twee, een, 1.0) is True)
    check('gelijkspel telt altijd', isRated(een, twee, 0.5) is True)
    check('tegen een andere tegenstander telt gewoon', isRated(een, drie, 1.0) is True)

    # Duels die niet meetelden, tellen ook niet mee voor de grens zelf.
    bewaarDuel(drie, een, rated=False)
    check('niet-meetellende duels tellen niet voor de rem',
          isRated(drie, een, 1.0) is True)

sys.exit(check.report())
