"""Test: na een fout antwoord krijgt de leerling het goede antwoord te zien.

Draaien vanuit de map `app`:

    python tests/test_goede_antwoord.py

Gespeeld via de echte socketverbinding, zoals de browser dat doet.
"""
import re
import sys
from urllib.parse import unquote

from helpers import Checks, loadApp

app = loadApp()

from src import sessionManager, socketio  # noqa: E402

check = Checks()
c = app.test_client()


def start(vorm, soort='oefenen'):
    data = {'KaartInput': 'Europa', 'mode': vorm, 'questions': ['Landen']}
    if soort == 'toets':
        data.update(soort='toets', toetsVragen='10')
    r = c.post('/', data=data)
    token = unquote(re.search(r'sessionToken=([^&]+)', r.headers['Location']).group(1))
    return token, sessionManager.findSession(token)


def antwoord(sok, token, waarde, hashed=False):
    sok.get_received()
    sok.emit('answerQuestion', {'sessionToken': token, 'awnser': waarde, 'hashed': hashed})
    return {m['name']: (m['args'][0] if m['args'] else None) for m in sok.get_received()}


# --- Meerkeuze / naam typen: "Dit is niet X, maar Y" -----------------------
token, sessie = start('MultipleChoise')
sok = socketio.test_client(app)
sok.emit('getQuestion', {'sessionToken': token})
gevraagd = sessie.currentQuestion.displayName
fout = 'Atlantis'
ontvangen = antwoord(sok, token, fout)
check('fout antwoord: de server zegt dat het fout is', 'questionIncorrect' in ontvangen, list(ontvangen))
data = ontvangen.get('questionIncorrect') or {}
check('en stuurt het goede antwoord mee', data.get('goed') == gevraagd, data)
check('en wat de leerling antwoordde', data.get('gegeven') == fout, data)

# Een goed antwoord geeft geen "fout"-bericht.
goedAntwoord = sessie.currentQuestion.allAnswers[0]
ontvangen = antwoord(sok, token, goedAntwoord)
check('goed antwoord: geen foutmelding', 'questionCorrect' in ontvangen and 'questionIncorrect' not in ontvangen)

# --- Aanwijzen: de goede plek krijgt een code mee om op te lichten ----------
token, sessie = start('ClickTheCountry')
sok = socketio.test_client(app)
sok.emit('getQuestion', {'sessionToken': token})
gevraagd = sessie.currentQuestion
anderePlek = next(q for q in sessie.questions if q is not gevraagd)
ontvangen = antwoord(sok, token, sessie.hash(anderePlek.id), hashed=True)
data = ontvangen.get('questionIncorrect') or {}
check('aanwijzen fout: de code van de goede plek komt mee', data.get('goedId') == sessie.hash(gevraagd.id), data)
check('en de naam van de plek waarop geklikt werd', data.get('gegeven') == anderePlek.displayName, data)

# --- Toets: daar komt het goede antwoord pas in de uitslag -----------------
token, sessie = start('MultipleChoise', 'toets')
sok = socketio.test_client(app)
sok.emit('getQuestion', {'sessionToken': token})
ontvangen = antwoord(sok, token, 'Atlantis')
check('bij een toets zegt de server tussendoor niets over goed of fout',
      'questionIncorrect' not in ontvangen and 'questionCorrect' not in ontvangen, list(ontvangen))

# --- De oefenpagina laat het zien ------------------------------------------
pagina = c.get('/learn?sessionToken=' + token).get_data(as_text=True)
check('de oefenpagina toont "Dit is niet ..., maar ..."', '", maar "' in pagina)
check('en licht bij aanwijzen de goede plek op', 'toonGoedePlek(data.goedId)' in pagina)

sys.exit(check.report())
