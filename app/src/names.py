"""Controle op namen die publiek zichtbaar worden.

Namen komen op de ranglijst, op het digibord bij de klassikale quiz en in een
duel bij je tegenstander te staan. Dat is een school vol pubers, en elke
brugklasser gaat proberen wat erdoor komt. Daarom:

1. Eerst wordt de naam op een paar manieren teruggerekend naar 'gewone'
   letters (zie `varianten`): l33tspeak (H1tl3r, k4nk3r, ph, vv), letters uit
   andere alfabetten die er hetzelfde uitzien (een Cyrillische a), tekens
   ertussen (k.a.n.k.e.r), herhaalde letters (kaaaanker) en achterstevoren
   (reltih).
2. Al die varianten gaan langs de woordenlijsten hieronder.
3. Daarnaast weigeren we 'rare' namen: toetsenbordgerammel, woorden zonder
   klinker, herhaalpatronen, te veel cijfers, websites, social-media-namen en
   telefoonnummers, en namen die doen alsof je docent of beheerder bent.

Het filter is bewust streng: liever een keer 'kies een andere naam' dan een
scheldwoord op het bord. Om gewone namen niet te raken staan er echte namen
in TOEGESTAAN die toevallig op een verboden woord lijken (Nazir, Kutlu, Lulof).
Glipt er toch iets door, of wordt een echte naam geweigerd: vul de lijsten
aan en zet een voorbeeld in tests/test_names.py.
"""
from __future__ import annotations

import re
import unicodedata

MIN_LENGTH = 2
MAX_LENGTH = 20
MAX_CIJFERS = 4

# Letters, cijfers, spatie, punt, streepje, liggend streepje en apostrof.
ALLOWED_RE = re.compile(r"^[^\W_]+(?:[ .'\-_][^\W_]+)*$", re.UNICODE)

# ----------------------------------------------------------------------
# Woordenlijsten (alles in kleine letters, zonder accenten)
# ----------------------------------------------------------------------

# Overal verboden, ook midden in een naam of samenstelling. Alleen woorden die
# nooit onschuldig in een naam zitten; uitzonderingen staan in TOEGESTAAN.
OVERAL = {
    # ziektes als scheldwoord
    'kanker', 'tyfus', 'tering', 'klere', 'kolere', 'cholera', 'pokke',
    # seks
    'neuk', 'fuck', 'fuk', 'fck', 'motherf', 'pussy', 'cunt', 'penis', 'vagina', 'piemel',
    'sperma', 'kutje', 'porno', 'porn', 'hentai', 'milf', 'dildo', 'orgasm', 'masturb',
    'blowjob', 'pijpbeurt', 'aftrek', 'boobs', 'tieten', 'titties', 'horny', 'geil',
    'onlyfans', 'verkracht', 'rapist', 'pedofiel', 'kinderlokker', 'sexy',
    # racisme en discriminatie
    'nigger', 'nigga', 'nikker', 'neger', 'kaffer', 'zwartjoekel', 'roetmop', 'makak',
    'spleetoog', 'geitenneuk', 'faggot', 'flikker', 'tranny', 'retard', 'mongool',
    'mongol', 'downie', 'spasticus', 'kankermarokkaan', 'jodenstreek', 'zigeuner',
    # extremisme en geweld
    'hitler', 'adolfh', 'nazi', 'siegheil', 'heilhitler', 'sieg heil', 'swastika',
    'hakenkruis', 'holocaust', 'auschwitz', 'gaskamer', 'gaskamers', 'genocide',
    'kkk', 'kukluxklan', 'whitepower', 'whitepride', '1488', 'jihad', 'taliban',
    'alqaeda', 'binladen', 'breivik', 'mussolini', 'terrorist', 'bomaanslag',
    'zelfmoord', 'suicide', 'killyourself', 'killjezelf', 'schooolshoot', 'schoolshoot',
    'moordenaar',
    # drugs
    'cocaine', 'heroine', 'heroin', 'crystalmeth', 'mdma', 'xtc', 'drugsdeal',
    'blowen', 'stoned',
    # scheldwoorden die als stuk van een woord ook altijd fout zijn
    'shit', 'bitch', 'asshole', 'klootzak', 'kloothommel', 'lullo', 'teringlijer',
    'mongolen', 'debiel', 'idioot', 'sukkel', 'hoerenjong', 'hoerenzoon',
    'bastard', 'wanker', 'slet', 'sloerie', 'kutwijf', 'trut', 'dickhead', 'dikzak',
    'motherfucker', 'sonofabitch', 'pedobear', 'jodenhaat', 'lekkerding', 'hotbabe',
    'sixtynine', 'allahuakbar', 'isstrijder', 'zwartepiet', 'apenkop', 'apekop', 'hitlerjugend',
}

# Verboden als begin of eind van een woord (kutjoch, lulhannes, joch-kut), maar
# niet ergens in het midden, want daar zitten ze in gewone namen.
BEGIN_OF_EIND = {
    'kut', 'lul', 'hoer', 'pik', 'kont', 'poep', 'pis', 'stront', 'drol', 'schijt',
    'homo', 'gay', 'cock', 'sex', 'seks', 'nazi', 'kkr', 'tfu', 'kys', 'slet', 'teef',
    'pedo', 'hater',
}

# Verboden als los woord (de hele naam, of een woord ervan).
LOS = {
    'kk', 'kkr', 'tfu', 'kys', 'lul', 'kut', 'pik', 'hoer', 'teef', 'eikel', 'spast',
    'mongo', 'homo', 'gay', 'fag', 'dick', 'cock', 'ass', 'arse', 'anal', 'anus', 'tits',
    'sex', 'seks', 'rape', 'nazi', 'meth', 'crack', 'lsd', 'wtf', 'stfu', 'fu', 'sos',
    'kill', 'killer', 'dood', 'death', 'satan', 'duivel', 'lucifer', 'jezus', 'god',
    'allah', 'heil', 'isis', 'ss', 'nsb', 'nsdap', 'reich', 'fuhrer', 'fuehrer',
    'poep', 'pis', 'pies', 'drol', 'stront', 'schijt', 'kont', 'reet', 'zeik', 'zeiken',
    'kots', 'kotsen', 'sukkel', 'debiel', 'idioot', 'loser', 'noob', 'nub', 'slet',
    'bitch', 'whore', 'slut', 'turd', 'piss', 'damn', 'crap', 'bollocks', 'bugger',
    'naakt', 'naked', 'nude', 'nudes', 'penis', 'tiet', 'tieten', 'borsten',
    'pedo', 'wiet', 'weed', 'coke', 'dealer', 'loser', 'reet', 'pies',
    'hasj', 'hash', 'joint', 'xanax', 'bom', 'bomb', 'bommen', 'hamas', 'hezbollah', 'osama',
    'stalin', 'autist', 'autistje', 'babe',
}

# Doen alsof je iemand anders bent. Als losse naam of als woord in de naam.
GERESERVEERD = {
    'admin', 'administrator', 'beheer', 'beheerder', 'moderator', 'mod', 'staff',
    'support', 'helpdesk', 'officieel', 'official', 'systeem', 'system', 'server',
    'docent', 'docente', 'leraar', 'lerares', 'leerkracht', 'juf', 'juffrouw', 'juffie', 'juffe',
    'meester',
    'meneer', 'mevrouw', 'mevr', 'dhr', 'mr', 'mrs', 'ms', 'rector', 'conrector',
    'directeur', 'directrice', 'mentor', 'mentrix', 'concierge', 'teamleider',
    'ichtopia', 'ichthus', 'ichthuslyceum',
    'anoniem', 'anonymous', 'onbekend', 'iedereen', 'niemand', 'gast', 'guest',
    'null', 'undefined', 'none', 'test', 'root',
    'claude', 'chatgpt', 'openai',
}

# Contactgegevens en reclame horen niet op een ranglijst vol kinderen.
CONTACT = ('www', 'http', 'insta', 'instagram', 'snap', 'snapchat', 'tiktok', 'discord',
           'whatsapp', 'telegram', 'youtube', 'twitch', 'telefoon', 'bel me', 'belme',
           'volg', 'follow', 'subscribe', 'abonneer')
DOMEINEN = re.compile(r'\.(com|nl|net|org|be|de|io|gg|tv|me|app|xyz|eu)\b', re.I)

# Rijen op het toetsenbord: rammen geeft deze letters achter elkaar.
TOETSENBORD = ('qwert', 'werty', 'ertyu', 'rtyui', 'tyuio', 'yuiop', 'asdfg', 'sdfgh',
               'dfghj', 'fghjk', 'ghjkl', 'zxcvb', 'xcvbn', 'cvbnm', 'azert', 'qwertz',
               'wasd', 'asdf', 'jkl', 'hjkl', 'qaz', 'wsx', 'edc', 'ujm', 'ikl')

# Echte namen en woorden die op iets verbodens lijken. Wordt per woord
# vergeleken; staat een woord hierin, dan telt het niet als verboden.
TOEGESTAAN = {
    'nazir', 'nazira', 'nazim', 'nazli', 'kutlu', 'kutluhan', 'lulof', 'lulofs', 'lulu',
    'lucas', 'dick', 'dickens', 'dirk', 'sanne', 'cassandra', 'cassie', 'assia', 'assia',
    'ashley', 'hassan', 'hassane', 'massa', 'jessica', 'essie', 'tessa', 'vanessa',
    'melissa', 'larissa', 'clarissa', 'nassim', 'yassin', 'yassine', 'yasser', 'assiel',
    'kassem', 'basse', 'basten', 'sebastian', 'sebastiaan', 'bastiaan', 'bas', 'kevin',
    'mathijs', 'methorst', 'hoera', 'fagel', 'kanaal', 'koekenbakker', 'pikachu',
    'pikkemaat', 'piket', 'koen', 'jessie', 'hitchcock', 'diede', 'dieke', 'diederik',
    'dieter', 'diemen', 'diego', 'sexton', 'essex', 'middlesex', 'sussex', 'title',
    'titus', 'tita', 'titia', 'titiaan', 'anaïs', 'anais', 'anouk', 'gaya', 'gayle',
    'gaby', 'homoet', 'poepjes', 'drolsma', 'pisa', 'pistache', 'kontich', 'reeta',
    'reetje', 'cockburn', 'scunthorpe', 'hancock', 'peacock', 'babcock', 'docks',
    'nikkie', 'nikki', 'niké', 'niek', 'nick', 'nicky', 'ginger', 'nigel', 'niger',
    'mongolie', 'wiets', 'wietse', 'wietze', 'coker', 'dealer', 'killian', 'kilian',
    'arsenal', 'assen', 'assendelft', 'basil', 'brass', 'grass', 'glass', 'class',
    'klaas', 'kees', 'jasper', 'kasper', 'casper', 'wasiem', 'ismail', 'isis', 'isa',
    'isabel', 'isabella', 'sexe', 'alexa', 'alexander', 'alex', 'axel', 'daniel',
    'dieuwke', 'kitty', 'titi', 'kontje', 'katja', 'koko', 'kokko', 'pijper', 'cockpit',
    'cocktail', 'scheijt', 'pissarro', 'mississippi', 'trutje', 'shitake', 'shiitake',
    'idiote', 'nikita', 'ignazio', 'torpedo', 'weeda', 'closer', 'janus', 'petit',
    'analiese', 'analisa', 'street', 'dieuwertje', 'kok', 'pizza', 'pizzas',
}
# Woorden uit OVERAL/BEGIN_OF_EIND die in deze namen voorkomen, tellen in
# die naam niet mee. Ook voor samengestelde controle: een woord moet in zijn
# geheel in TOEGESTAAN staan.

# Voor achterstevoren kijken we alleen naar de echt zware woorden.
ACHTERSTEVOREN = {'hitler', 'kanker', 'nazi', 'nigger', 'fuck', 'neuk', 'tyfus', 'hoer',
                  'kut', 'lul', 'penis', 'sex', 'tering'}

# ----------------------------------------------------------------------
# Normaliseren
# ----------------------------------------------------------------------

# l33tspeak per teken. Meerdere mogelijkheden: '1' kan een i of een l zijn.
LEET = {
    '0': 'o', '1': 'il', '2': 'z', '3': 'e', '4': 'a', '5': 's', '6': 'gb', '7': 't',
    '8': 'b', '9': 'g', '@': 'a', '$': 's', '!': 'i', '|': 'il', '€': 'e', '£': 'l', 'v': 'vu',
    '+': 't', '(': 'c', '¢': 'c', '¥': 'y', 'ß': 'ss',
}
LEET_REEKSEN = [('ph', 'f'), ('vv', 'w'), ('ck', 'k'), ('kk', 'k'), ('qu', 'kw'),
                ('ij', 'y'), ('ei', 'y'), ('x', 'ks'), ('c', 'k'), ('q', 'k'), ('z', 's')]

# Letters uit andere alfabetten die op Latijnse letters lijken.
LOOKALIKE = str.maketrans({
    'а': 'a', 'в': 'b', 'е': 'e', 'ё': 'e', 'к': 'k', 'м': 'm', 'н': 'h', 'о': 'o',
    'р': 'p', 'с': 'c', 'т': 't', 'у': 'y', 'х': 'x', 'ѕ': 's', 'і': 'i', 'ј': 'j',
    'ԁ': 'd', 'ӏ': 'l', 'ɡ': 'g', 'ɑ': 'a', 'ο': 'o', 'α': 'a', 'ν': 'v', 'ρ': 'p',
    'τ': 't', 'κ': 'k', 'ι': 'i', 'υ': 'u', 'χ': 'x', 'β': 'b', 'ε': 'e', 'η': 'n',
    'μ': 'u', 'ω': 'w', 'А': 'a', 'В': 'b', 'Е': 'e', 'К': 'k', 'М': 'm', 'Н': 'h',
    'О': 'o', 'Р': 'p', 'С': 'c', 'Т': 't', 'Х': 'x', 'І': 'i',
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


def _basis(name: str) -> str:
    """Kleine letters, zonder accenten, lookalikes naar gewone letters."""
    text = unicodedata.normalize('NFKC', cleanName(name)).translate(LOOKALIKE)
    return stripAccents(text).lower()


def _leetVarianten(text: str, maxVarianten: int = 64) -> list[str]:
    """Alle manieren waarop de cijfers en tekens als letters gelezen kunnen worden."""
    varianten = ['']
    for ch in text:
        opties = LEET.get(ch, ch)
        varianten = [v + o for v in varianten for o in opties][:maxVarianten]
    return varianten


def _samentrekken(text: str) -> str:
    """Herhaalde letters tot een: kaaaanker -> kanker."""
    return re.sub(r'(.)\1+', r'\1', text)


def _klank(text: str) -> str:
    """Spelvarianten gelijktrekken: ph=f, ck=k, c=k, z=s, ij/ei=y."""
    for van, naar in LEET_REEKSEN:
        text = text.replace(van, naar)
    return _samentrekken(text)


def varianten(name: str) -> set[str]:
    """Alle vormen waarin we een naam met de woordenlijsten vergelijken, aan
    elkaar geschreven (zonder spaties en tekens)."""
    basis = _basis(name)
    vormen = set()
    for v in _leetVarianten(basis):
        plat = re.sub(r'[^a-z]+', '', v)
        if plat:
            vormen |= {plat, _samentrekken(plat), _klank(plat)}
    return vormen


def woorden(name: str) -> list[list[str]]:
    """Per woord in de naam: de varianten van dat woord. De eerste is het
    woord zoals het er staat (kleine letters, zonder accenten en tekens)."""
    uit = []
    for stuk in re.split(r"[ .'\-_]+", _basis(name)):
        if not stuk:
            continue
        zoalsGetypt = re.sub(r'[^a-z0-9]+', '', stuk)
        vormen = set()
        # Ook zonder de cijfers: Admin123, Kanker2012.
        for bron in {stuk, re.sub(r'[0-9]+', '', stuk)}:
            for v in _leetVarianten(bron):
                plat = re.sub(r'[^a-z]+', '', v)
                if plat:
                    vormen |= {plat, _samentrekken(plat), _klank(plat)}
        vormen.discard(zoalsGetypt)
        uit.append([zoalsGetypt] + sorted(vormen))
    return uit


def _zonderKlank(woord: str) -> set[str]:
    """De vormen van een woord met alleen l33tspeak en samentrekken, zonder
    spelling gelijk te trekken (c=k, z=s). Voor korte woorden aan begin of
    eind: met klank wordt Kok 'cock' en Pizza 'pisa'."""
    vormen = set()
    for bron in {woord, re.sub(r'[0-9]+', '', woord)}:
        for v in _leetVarianten(bron):
            plat = re.sub(r'[^a-z]+', '', v)
            if plat:
                vormen |= {plat, _samentrekken(plat)}
    return vormen


def _gelijkgetrokken(woordenlijst) -> set[str]:
    """De woorden zelf plus hun samengetrokken en klank-vorm. Een ingekorte
    vorm moet minstens drie letters houden: 'kkk' mag geen 'k' worden, want
    die zit in bijna elke naam."""
    uit = set(woordenlijst)
    for w in woordenlijst:
        for vorm in (_samentrekken(w), _klank(w)):
            if len(vorm) >= 3:
                uit.add(vorm)
    return uit


_OVERAL = {w.replace(' ', '') for w in OVERAL}
_OVERAL_ALLES = _gelijkgetrokken(_OVERAL)
_BEGIN_OF_EIND = _gelijkgetrokken(BEGIN_OF_EIND)  # korte woorden: zie _woordIsVerboden
_LOS = _gelijkgetrokken(LOS)
_GERESERVEERD = _gelijkgetrokken(GERESERVEERD)
_ACHTERSTEVOREN = _gelijkgetrokken(ACHTERSTEVOREN)
_TOEGESTAAN = set(TOEGESTAAN)


def _isToegestaan(woordVarianten) -> bool:
    """Is dit woord, precies zo getypt, een echte naam? De eerste vorm in de
    lijst is altijd het woord zoals het er staat (zie woorden()). Via
    l33tspeak of samentrekken wordt een woord nooit 'toegestaan': anders zou
    n1gger via 'niger' (de rivier) erdoor komen."""
    return bool(woordVarianten) and woordVarianten[0] in _TOEGESTAAN


def _woordIsVerboden(vormen) -> str | None:
    ruw = _zonderKlank(vormen[0]) if vormen else set()
    for vorm in vormen:
        for slecht in _OVERAL_ALLES:
            if slecht in vorm:
                return slecht
        if vorm in _LOS:
            return vorm
        for slecht in _BEGIN_OF_EIND:
            if len(slecht) <= 3 and vorm not in ruw:
                continue
            if vorm == slecht or (len(vorm) > len(slecht) and (vorm.startswith(slecht) or vorm.endswith(slecht))):
                return slecht
        terug = vorm[::-1]
        for slecht in _ACHTERSTEVOREN:
            if len(slecht) >= 4 and slecht in terug:
                return slecht + ' (achterstevoren)'
    return None


def _isPrecies(vormen) -> str | None:
    """Vormt dit samen precies een verboden woord? Voor 'K U T' en 'kan ker'."""
    for vorm in vormen:
        if vorm in _LOS or vorm in _OVERAL_ALLES or vorm in _BEGIN_OF_EIND:
            return vorm
    return None


def verbodenWoord(name: str) -> str | None:
    """Het verboden woord dat in de naam zit (voor de logs en de tests), of None."""
    if re.search(r'14[\W_]*88|88[\W_]*14', name):
        return '1488'
    # Getallen die als code gebruikt worden (seks, wiet). 88 los mag wel:
    # dat is te vaak gewoon een geboortejaar.
    if re.search(r'(?<!\d)(69|420)(?!\d)', name):
        return re.search(r'(?<!\d)(69|420)(?!\d)', name).group(1)
    perWoord = woorden(name)
    for vormen in perWoord:
        if _isToegestaan(vormen):
            continue
        slecht = _woordIsVerboden(vormen)
        if slecht:
            return slecht
    # Losse letters achter elkaar (K U T, f.u.c.k): samen controleren.
    stukken = re.split(r"[ .'\-_]+", _basis(name))
    korte = []
    for stuk in stukken + ['']:
        if 0 < len(stuk) <= 2:
            korte.append(stuk)
            continue
        if len(korte) >= 2:
            slecht = _isPrecies(varianten(''.join(korte)))
            if slecht:
                return slecht
        korte = []
    # Een woord in tweeen geknipt (kan ker, hit ler): twee buren samen.
    for links, rechts in zip(stukken, stukken[1:]):
        slecht = _isPrecies(varianten(links + rechts))
        if slecht and re.sub(r'[^a-z0-9]+', '', links + rechts) not in _TOEGESTAAN:
            return slecht
    return None


def containsBlockedWord(name: str) -> bool:
    return verbodenWoord(name) is not None


def gereserveerd(name: str) -> bool:
    perWoord = woorden(name)
    if any(v in _GERESERVEERD for v in varianten(name)):
        return True
    return any(v in _GERESERVEERD for w in perWoord for v in w)


def _raar(name: str) -> str | None:
    """Uitleg waarom de naam 'raar' is, of None."""
    laag = _basis(name)
    plat = re.sub(r'[^a-z0-9]+', '', laag)
    letters = re.sub(r'[^a-z]+', '', laag)

    if any(c in laag.replace(' ', '') for c in CONTACT) or DOMEINEN.search(name) \
            or re.search(r'(?:\+31|0031|\b06)[ .\-]?\d', laag):
        return 'Zet geen websites, social-media-namen of telefoonnummers in je naam.'
    cijfers = sum(ch.isdigit() for ch in name)
    if cijfers > MAX_CIJFERS or (cijfers and cijfers >= len(letters)):
        return f'Gebruik vooral letters: hooguit {MAX_CIJFERS} cijfers, en meer letters dan cijfers.'
    if re.search(r'(.)\1\1', plat):
        return 'Niet meer dan twee dezelfde tekens achter elkaar.'
    if re.search(r'(..+?)\1{2,}', plat):
        return 'Geen herhaalpatronen zoals hahaha of abcabc.'
    if any(rij in letters or rij[::-1] in letters for rij in TOETSENBORD if len(rij) >= 4) \
            or sum(rij in letters for rij in TOETSENBORD) >= 2:
        return 'Dat lijkt op rammen op het toetsenbord. Kies een echte naam of bijnaam.'
    for woord in re.split(r'[^a-z]+', laag):
        if len(woord) >= 5 and not re.search(r'[aeiouy]', woord):
            return 'Een woord in je naam heeft geen klinker. Kies een naam die je kunt uitspreken.'
        if len(woord) >= 7 and re.search(r'[^aeiouy]{6,}', woord):
            return 'Een woord in je naam heeft heel veel medeklinkers achter elkaar.'
    return None


def checkName(name, *, minLength: int = MIN_LENGTH, maxLength: int = MAX_LENGTH) -> str:
    """Geef de opgeschoonde naam terug, of gooi NameError_ met een uitleg."""
    name = cleanName(name)

    if len(name) < minLength:
        raise NameError_(f'Je naam moet minstens {minLength} tekens lang zijn.')
    if len(name) > maxLength:
        raise NameError_(f'Je naam mag hooguit {maxLength} tekens lang zijn.')
    if not ALLOWED_RE.match(name):
        raise NameError_('Gebruik alleen letters, cijfers, spaties, punten en streepjes.')
    if any(ord(ch) > 0x24F and ch.isalpha() and ch.translate(LOOKALIKE) == ch for ch in name):
        raise NameError_('Gebruik gewone letters (a tot z, met accenten mag).')

    letters = sum(1 for ch in name if ch.isalpha())
    if letters < 2:
        raise NameError_('Er moeten minstens twee letters in je naam staan.')
    if gereserveerd(name):
        raise NameError_('Deze naam is gereserveerd: je mag niet doen alsof je een docent of beheerder bent.')
    if containsBlockedWord(name):
        raise NameError_('Deze naam kan niet: hij bevat een woord dat we niet toestaan.')
    uitleg = _raar(name)
    if uitleg:
        raise NameError_(uitleg)
    return name


def isAcceptable(name) -> bool:
    try:
        checkName(name)
    except NameError_:
        return False
    return True


def naamSleutel(name: str) -> str:
    """Vorm om te kijken of twee namen te veel op elkaar lijken: F1oris,
    FIoris en Flor1s worden allemaal 'floris'. Hoofdletters, accenten,
    leestekens, cijfers die op letters lijken en dubbele letters tellen niet."""
    basis = _basis(name)
    for cijfer, letter in (('0', 'o'), ('1', 'l'), ('3', 'e'), ('4', 'a'), ('5', 's'), ('7', 't'), ('8', 'b')):
        basis = basis.replace(cijfer, letter)
    basis = basis.replace('i', 'l')      # hoofdletter I en kleine l lijken op elkaar
    plat = re.sub(r'[^a-z0-9]+', '', basis)
    return _samentrekken(plat)
