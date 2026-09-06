"""Controle op namen die publiek zichtbaar worden.

Namen komen op de ranglijst, op het digibord bij de klassikale quiz en in een
duel bij je tegenstander te staan. Dat is een klas vol pubers, dus filteren we
op drie dingen: lengte, rare tekens en scheldwoorden.

Het filter is bewust streng aan de kant van de bekende trucs (l3tspeak, extra
tekens ertussen) en mild bij twijfel: liever een keer "kies een andere naam"
dan een scheldwoord op het bord.
"""
from __future__ import annotations

import re
import unicodedata

MIN_LENGTH = 2
MAX_LENGTH = 20

# Letters, cijfers, spatie, punt, streepje, liggend streepje en apostrof.
ALLOWED_RE = re.compile(r"^[^\W_]+(?:[ .'\-_][^\W_]+)*$", re.UNICODE)

# Woorden die alleen als heel woord verboden zijn. Als losse letterreeks komen
# ze in gewone namen voor (denk aan "hoera", "Lulof"), dus geen substring-match.
BLOCKED_WORDS = {
    # nederlands
    'kut', 'kutje', 'lul', 'lullo', 'pik', 'piemel', 'eikel', 'sukkel', 'debiel',
    'mongool', 'spast', 'spasticus', 'kanker', 'tering', 'tyfus', 'klere',
    'kolere', 'hoer', 'slet', 'sloerie', 'trut', 'teef', 'bitch',
    'neuken', 'neuk', 'wippen', 'aftrekken', 'pijpen', 'sperma', 'penis',
    'vagina', 'kont', 'reet', 'poep', 'poepen', 'schijt', 'stront', 'drol',
    'pis', 'pissen', 'zeiken', 'kotsen', 'flikker', 'homo', 'nicht',
    'mietje', 'kkr', 'kk', 'tfu',
    # engels
    'fuck', 'fucker', 'fucking', 'shit', 'shite', 'crap', 'dick', 'cock',
    'pussy', 'cunt', 'whore', 'slut', 'bastard', 'asshole', 'arsehole', 'ass',
    'arse', 'anal', 'anus', 'boobs', 'tits', 'titties', 'porn', 'porno',
    'sex', 'sexy', 'horny', 'wank', 'wanker', 'jerkoff', 'bollocks', 'bugger',
    'damn', 'piss', 'turd', 'milf', 'hentai', 'rape', 'nazi', 'fag',
    'meth', 'kys',
}

# Deze worden overal in de naam herkend, ook midden in een woord. Alleen voor
# woorden die nooit onschuldig in een naam voorkomen.
BLOCKED_ANYWHERE = (
    'kanker', 'kankerlijer', 'tyfuslijer', 'neuken', 'verkrachting',
    'fuck', 'motherfucker', 'nigger', 'nigga', 'neger', 'faggot',
    'retard', 'kaffer', 'zwartjoekel', 'jodenstreek', 'hitler',
    'pedofiel', 'kinderlokker', 'zelfmoord', 'suicide',
    'cocaine', 'heroine',
)

# Namen die doen alsof je iets bent wat je niet bent.
RESERVED = {
    'admin', 'administrator', 'beheerder', 'moderator', 'mod', 'docent',
    'leraar', 'lerares', 'meneer', 'mevrouw', 'systeem', 'system', 'server',
    'topo', 'ichthus', 'ichthuslyceum', 'anoniem', 'onbekend', 'iedereen',
    'null', 'undefined', 'none',
}

# l3etspeak terugvertalen voordat we vergelijken.
LEET = str.maketrans({
    '4': 'a', '@': 'a', '8': 'b', '(': 'c', '3': 'e', '6': 'g', '9': 'g',
    '1': 'i', '!': 'i', '|': 'i', '0': 'o', '5': 's', '$': 's', '7': 't',
    '+': 't', '2': 'z',
})


class NameError_(ValueError):
    """Naam afgekeurd; de tekst is bedoeld om aan de gebruiker te tonen."""


def stripAccents(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    return ''.join(c for c in text if not unicodedata.combining(c))


def cleanName(name) -> str:
    """Haal onzichtbare tekens en dubbele spaties weg. Verandert niets aan de letters."""
    name = ''.join(ch for ch in str(name) if ch.isprintable())
    return ' '.join(name.split())


def _compare(name: str) -> str:
    """De vorm waarop we met de woordenlijst vergelijken."""
    text = stripAccents(cleanName(name).lower()).translate(LEET)
    return re.sub(r'[^a-z0-9]+', '', text)


def _words(name: str) -> list[str]:
    text = stripAccents(cleanName(name).lower()).translate(LEET)
    return [w for w in re.split(r'[^a-z0-9]+', text) if w]


def containsBlockedWord(name: str) -> bool:
    """Staat er een scheldwoord in, ook met streepjes of cijfers erdoorheen?"""
    squashed = _compare(name)
    if any(bad in squashed for bad in BLOCKED_ANYWHERE):
        return True
    if any(word in BLOCKED_WORDS for word in _words(name)):
        return True
    # "K-U-T" en "f.u.c.k" worden pas na het samentrekken zichtbaar. Bewust
    # alleen als de hele naam zo'n woord is: op losse letterreeksen matchen
    # sloopt gewone namen (Nazir, Methorst, Hoera).
    return squashed in BLOCKED_WORDS


def checkName(name, *, minLength: int = MIN_LENGTH, maxLength: int = MAX_LENGTH) -> str:
    """Geef de opgeschoonde naam terug, of gooi NameError_ met een uitleg."""
    name = cleanName(name)

    if len(name) < minLength:
        raise NameError_(f'Je naam moet minstens {minLength} tekens lang zijn.')
    if len(name) > maxLength:
        raise NameError_(f'Je naam mag hooguit {maxLength} tekens lang zijn.')
    if not ALLOWED_RE.match(name):
        raise NameError_('Gebruik alleen letters, cijfers, spaties, punten en streepjes.')

    letters = sum(1 for ch in name if ch.isalpha())
    if letters < 2:
        raise NameError_('Er moeten minstens twee letters in je naam staan.')
    if re.search(r'(.)\1\1\1', name.lower()):
        raise NameError_('Niet meer dan drie dezelfde tekens achter elkaar.')
    if _compare(name) in RESERVED or any(w in RESERVED for w in _words(name)):
        raise NameError_('Deze naam is gereserveerd, kies een andere.')
    if containsBlockedWord(name):
        raise NameError_('Deze naam kan niet: hij bevat een woord dat we niet toestaan.')

    return name


def isAcceptable(name) -> bool:
    try:
        checkName(name)
    except NameError_:
        return False
    return True
