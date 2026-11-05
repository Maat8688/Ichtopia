"""Test van wat de server meestuurt voor "x van y gekend" op de startpagina.

Draaien vanuit de map `app`:

    python tests/test_voortgang.py

Vroeger bewaarde de browser alleen "zoveel van zoveel in deze sessie", zodat
er na alleen de provincies "12 van 12 gekend" bij Nederland stond. Nu stuurt
de server welke vragen je kent (als code) en hoeveel vragen de hele kaart
heeft op jouw niveau; de browser telt de codes van alle sessies op.
"""
import re
import sys
from urllib.parse import unquote

from helpers import Checks, loadApp

app = loadApp()

from src import sessionManager  # noqa: E402

check = Checks()
c = app.test_client()


def sessie(kaart, onderdelen, niveau=None):
    data = {'KaartInput': kaart, 'mode': 'MultipleChoise', 'questions': onderdelen}
    if niveau:
        data['niveau'] = niveau
    r = c.post('/', data=data)
    return sessionManager.findSession(unquote(re.search(r'sessionToken=([^&]+)', r.headers['Location']).group(1)))


def kenAlles(s, aantal):
    """Beantwoord `aantal` vragen meteen goed, zodat ze 'gekend' zijn."""
    for _ in range(aantal):
        s.awnserQuestion(s.currentQuestion.allAnswers[0], False)
        if s.nextQuestion():
            break


provincies = sessie('Nederland', ['Provincies'])
stand = provincies.getProgresBar()
check('alleen provincies: de sessie heeft 12 vragen', stand['totalQuestions'] == 12)
check('maar de hele kaart heeft er 98', stand['kaartTotaal'] == 98, stand['kaartTotaal'])
check('nog niets gekend: geen codes', stand['gekendIds'] == [])

kenAlles(provincies, 12)
stand = provincies.getProgresBar()
check('alles goed: 12 codes van gekende vragen', len(stand['gekendIds']) == 12, len(stand['gekendIds']))

opnieuw = sessie('Nederland', ['Provincies'])
kenAlles(opnieuw, 12)
check('dezelfde vragen in een nieuwe sessie geven dezelfde codes (anders telt de browser dubbel)',
      set(opnieuw.getProgresBar()['gekendIds']) == set(stand['gekendIds']))

wateren = sessie('Nederland', ['Wateren'])
kenAlles(wateren, 3)
check('andere onderdelen geven andere codes',
      not (set(wateren.getProgresBar()['gekendIds']) & set(stand['gekendIds'])))

check('Zuid-Amerika op havo: 40 vragen in totaal', sessie('Zuid-Amerika', ['Landen'], 'havo').getProgresBar()['kaartTotaal'] == 40)
check('Zuid-Amerika op vwo: 88', sessie('Zuid-Amerika', ['Landen'], 'vwo').getProgresBar()['kaartTotaal'] == 88)

start = c.get('/').get_data(as_text=True)
check('de startpagina leest de nieuwe stand en ruimt de oude op',
      'topo.gekend' in start and 'removeItem("topo.progress")' in start)

sys.exit(check.report())
