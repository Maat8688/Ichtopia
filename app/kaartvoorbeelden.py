"""Maak de voorbeeldkaarten voor de startpagina (static/img/kaart-*.svg).

    cd app
    python kaartvoorbeelden.py

De voorbeelden worden gemaakt uit dezelfde kaart als het spel zelf
(templates/partials/mapSvg.html), dus met dezelfde kleuren, dezelfde grenzen
en hetzelfde vergrootglas om het Midden-Oosten. Zo kan een voorbeeld er nooit
anders uitzien dan de kaart waarop je oefent. Draai dit opnieuw als er een
kaart in data/maps verandert.

Het voorbeeld is een los plaatje (<img>), dus de kleuren uit
design-tokens.css komen er hier in te staan, en alles wat met klikken of de
stand van een vraag te maken heeft, valt weg. De getallen blijven zoals ze
zijn: de vormen gebruiken relatieve coördinaten, en afronden laat elk land
een stukje verschuiven, met een streep zee tussen de grenzen als gevolg.
"""
import os
import re
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
os.chdir(HIER)
sys.path.insert(0, HIER)
os.environ.setdefault('SECRET_KEY', 'voorbeelden')
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('LOG_DIR', os.path.join(HIER, 'log'))

from sqlalchemy import ARRAY  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(ARRAY, 'sqlite')
def _arrayAlsTekst(element, compiler, **kw):
    return 'TEXT'


from flask import render_template  # noqa: E402

from src import app  # noqa: E402
from src.kahoot import MAP_FILES  # noqa: E402
from src.map import DECOR_CATEGORIES, mapSession  # noqa: E402


def kleuren() -> str:
    """De kleuren uit design-tokens.css, voor binnen het plaatje."""
    with open(os.path.join('static', 'css', 'design-tokens.css'), encoding='utf-8') as f:
        tokens = f.read()
    blok = re.search(r':root\s*{(.*?)}', tokens, re.S).group(1)
    regels = re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', blok)
    return 'svg{' + ''.join(f'{naam}:{waarde.strip()};' for naam, waarde in regels) + '}'


def voorbeeld(naam: str, bestand: str) -> str:
    # Alleen landen en provincies, getekend zoals in het spel (als vraag die
    # nog open staat): dan is elke grens één lijn. Steden, rivieren en
    # gebergten vallen weg; een voorbeeld laat alleen zien welke kaart het is.
    sessie = mapSession.fromSVG(bestand, 'MultipleChoise', list(DECOR_CATEGORIES), None)
    with app.test_request_context('/'):
        svg = render_template('partials/mapSvg.html', map=sessie)

    # In het spel staat de opmaak in een <style> naast de kaart; in een los
    # plaatje moet hij erin, samen met de kleuren.
    stijl = re.search(r'<style>(.*?)</style>', svg, re.S).group(1)
    svg = svg[svg.index('<svg'):svg.index('</svg>') + 6]
    # Geen id's die de stand of een vraag verraden.
    svg = re.sub(r' (Id|state|tabindex|role)="[^"]*"', '', svg)
    svg = re.sub(r' style="aspect-ratio:[^"]*"', ' preserveAspectRatio="xMidYMid meet"', svg, count=1)
    kop = svg.index('>') + 1
    svg = svg[:kop] + '<style>' + kleuren() + stijl + '</style>' + svg[kop:]
    svg = re.sub(r'\n\s*\n', '\n', svg)
    return svg


if __name__ == '__main__':
    for naam, bestand in MAP_FILES.items():
        uit = os.path.join('static', 'img', f'kaart-{naam}.svg')
        inhoud = voorbeeld(naam, bestand)
        with open(uit, 'w', encoding='utf-8') as f:
            f.write(inhoud)
        print(f'{uit}: {len(inhoud) // 1024} kB')
