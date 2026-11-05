"""Test van het inlezen van de kaarten.

Draaien vanuit de map `app`:

    python tests/test_kaart.py

Vraag je alleen steden, dan moeten de provincies er nog wel als land onder
liggen. Anders staan de steden in zee.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import Checks, loadApp   # noqa: E402

loadApp()

from src.map import mapSession   # noqa: E402

check = Checks()

alleenSteden = mapSession.fromSVG('data/maps/Nederland.svg', 'MultipleChoise', ['Steden'])
check('alleen steden gevraagd', {q.category for q in alleenSteden.questions} == {'Steden'},
      {q.category for q in alleenSteden.questions})
decor = [el for el in alleenSteden.backgroundElements if 'class="decor"' in el]
check('de twaalf provincies liggen er als land onder', len(decor) == 12, len(decor))
check('zonder id, dus geen dubbele ids met de vragen',
      all(' id="' not in el.split('>', 1)[0] for el in decor))
check('zonder antwoorden erin', all('<awnser' not in el for el in decor))

metProvincies = mapSession.fromSVG('data/maps/Nederland.svg', 'MultipleChoise', ['Steden', 'Provincies'])
decorMet = [el for el in metProvincies.backgroundElements if 'class="decor"' in el]
check('worden provincies gevraagd, dan niet ook nog als achtergrond', len(decorMet) == 0, len(decorMet))

wereld = mapSession.fromSVG('data/maps/Wereld.svg', 'MultipleChoise', ['Hoofdsteden'])
check('wereld met alleen hoofdsteden houdt de landen als land',
      any('class="decor"' in el for el in wereld.backgroundElements))

sys.exit(check.report())
