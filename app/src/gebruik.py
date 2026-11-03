"""Bijhouden hoe de site gebruikt wordt, en dat optellen voor /statistieken.

Wat er wordt opgeslagen staat in models.Gebruik. Kort:

- elk bekeken pagina (alleen echte pagina's, geen plaatjes of websockets);
- elke oefensessie die begint, en wat er gebeurde als hij werd afgemaakt;
- elke klassikale quiz: aangemaakt, gestart (met hoeveel leerlingen) en klaar.

Geen namen, geen e-mail, geen IP-adressen. Om toch te kunnen tellen hoeveel
verschillende mensen er op een dag waren, krijgt elke bezoeker per dag een
code: een hash van zijn IP-adres en browser met een geheim dat elke dag nieuw
is en alleen in het geheugen staat. Morgen krijgt dezelfde leerling dus een
andere code, en na een herstart van de server ook. Terugrekenen naar een
IP-adres kan niet, want het geheim wordt nergens bewaard.

Opslaan mag de site nooit laten vastlopen: lukt het niet, dan wordt de
gebeurtenis overgeslagen en gaat alles verder.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import statistics
import threading
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import request

TIJDZONE = ZoneInfo('Europe/Amsterdam')

WEEKDAGEN = ['maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag']
WEEKDAGEN_KORT = ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo']
MAANDEN_KORT = ['jan', 'feb', 'mrt', 'apr', 'mei', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec']
VORMEN = {1: 'Meerkeuze', 2: 'Naam typen', 3: 'Aanwijzen'}
PERIODES = {'7': 7, '30': 30, '90': 90, 'alles': None}

# Welke adressen welke pagina zijn. Wat hier niet in staat, telt niet mee
# (de statistiekenpagina zelf, inloggen, foutpagina's).
PAGINAS = [
    (re.compile(r'^/$'), 'Startpagina'),
    (re.compile(r'^/learn$'), 'Oefenen'),
    (re.compile(r'^/join$'), 'Meedoen aan quiz'),
    (re.compile(r'^/play/[^/]+$'), 'Quiz spelen'),
    (re.compile(r'^/host$'), 'Quiz maken'),
    (re.compile(r'^/host/login$'), 'Docentcode'),
    (re.compile(r'^/host/[^/]+$'), 'Digibord'),
]


# ----------------------------------------------------------------------
# Vastleggen
# ----------------------------------------------------------------------
_zout = {'dag': None, 'geheim': ''}
_zoutLock = threading.Lock()


def _nuUtc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def bezoekerCode() -> str:
    """Code voor deze bezoeker, alleen vandaag geldig. Zie de uitleg bovenaan."""
    vandaag = datetime.now(TIJDZONE).date()
    with _zoutLock:
        if _zout['dag'] != vandaag:
            _zout['dag'] = vandaag
            _zout['geheim'] = secrets.token_hex(16)
        geheim = _zout['geheim']
    ip = request.remote_addr or ''
    browser = request.headers.get('User-Agent', '')[:200]
    return hashlib.sha256(f'{geheim}|{ip}|{browser}'.encode()).hexdigest()[:16]


def apparaatSoort(browser: str) -> str:
    browser = browser or ''
    if re.search(r'iPad|Tablet', browser) or ('Android' in browser and 'Mobile' not in browser):
        return 'tablet'
    if re.search(r'Mobi|iPhone|Android', browser):
        return 'telefoon'
    return 'computer'


def paginaNaam(pad: str) -> str | None:
    for patroon, naam in PAGINAS:
        if patroon.match(pad):
            return naam
    return None


def leg(soort: str, **velden):
    """Sla een gebeurtenis op. Gaat het mis, dan gaat de site gewoon door."""
    from . import app
    from .models import Gebruik, db
    try:
        with app.app_context():
            db.session.add(Gebruik(tijd=_nuUtc(), soort=soort, **velden))
            db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        app.logger.warning('Gebruik niet opgeslagen (%s)', soort, exc_info=True)


def legSessie(soort: str, sessie, **velden):
    """Een oefensessie die begint of klaar is, met wat erbij hoort."""
    try:
        bezoeker, apparaat = bezoekerCode(), apparaatSoort(request.headers.get('User-Agent'))
        plek = waarVandaan()
    except RuntimeError:            # buiten een verzoek, bijvoorbeeld in een test
        bezoeker, apparaat, plek = None, None, {}
    onderdelen = sorted({q.category for q in sessie.questions if q.category})
    leg(soort,
        bezoeker=bezoeker, apparaat=apparaat, **plek,
        kaart=sessie.mapName, vorm=VORMEN.get(sessie.sessionMode, str(sessie.sessionMode)),
        onderdelen=','.join(onderdelen)[:200], niveau=getattr(sessie, 'niveau', None),
        vragen=len(sessie.questions), **velden)


def legKlaar(sessie, uitslag: dict):
    """Afgemaakte oefensessie: pogingen, duur en welke plekken fout gingen."""
    fout = {}
    for vraag in uitslag.get('questionBreakdown', []):
        extra = int(vraag.get('tries', 0)) - 1
        if extra > 0:
            fout[str(vraag.get('name'))] = extra
    legSessie('oefenen_klaar', sessie,
              pogingen=int(uitslag.get('totalGuesses') or 0),
              duur=int(uitslag.get('time') or 0),
              fout=json.dumps(fout, ensure_ascii=False) if fout else None)


def legQuiz(soort: str, game, spelers: int | None = None):
    leg(soort, kaart=game.mapName, vorm=VORMEN.get(game.mode, str(game.mode)),
        onderdelen=','.join(sorted(game.categories))[:200] if getattr(game, 'categories', None) else None,
        vragen=len(game.questions), spelers=spelers)


def waarVandaan() -> dict:
    """Land, provincie en of het op school is, voor dit verzoek. Het IP-adres
    wordt alleen hier gebruikt om op te zoeken en daarna vergeten."""
    from . import locatie
    ip = request.remote_addr
    land, provincie = locatie.zoekOp(ip)
    return {'land': land, 'provincie': provincie, 'school': locatie.opSchool(ip)}


# Kolommen die er later bij zijn gekomen: (naam, type in SQL).
LATERE_KOLOMMEN = [('land', 'VARCHAR(2)'), ('provincie', 'VARCHAR(20)'), ('school', 'BOOLEAN')]


def zorgVoorKolommen():
    """Voeg ontbrekende kolommen toe aan een tabel gebruik die er al was.

    db.create_all() maakt wel nieuwe tabellen, maar past een bestaande niet
    aan. Gaat het mis, dan start de site toch; het tellen van de plek werkt
    dan alleen niet."""
    from . import app
    from .models import db
    try:
        from sqlalchemy import inspect, text
        inspectie = inspect(db.engine)
        if not inspectie.has_table('gebruik'):
            return
        bestaand = {k['name'] for k in inspectie.get_columns('gebruik')}
        with db.engine.begin() as verbinding:
            for naam, soort in LATERE_KOLOMMEN:
                if naam not in bestaand:
                    verbinding.execute(text(f'ALTER TABLE gebruik ADD COLUMN {naam} {soort}'))
    except Exception:
        app.logger.warning('Kolommen van gebruik niet bijgewerkt', exc_info=True)


def registreerBezoeken(app):
    """Na elk verzoek: was het een echte pagina, dan tellen we hem."""
    @app.after_request
    def telBezoek(response):
        try:
            if (request.method == 'GET' and response.status_code == 200
                    and response.mimetype == 'text/html'):
                naam = paginaNaam(request.path)
                if naam:
                    leg('bezoek', pagina=naam, bezoeker=bezoekerCode(),
                        apparaat=apparaatSoort(request.headers.get('User-Agent')),
                        **waarVandaan())
        except Exception:
            app.logger.warning('Bezoek niet geteld', exc_info=True)
        return response


# ----------------------------------------------------------------------
# Optellen
# ----------------------------------------------------------------------
def _lokaal(utc: datetime) -> datetime:
    return utc.replace(tzinfo=timezone.utc).astimezone(TIJDZONE)


def _dagLabel(d: date) -> str:
    return f'{WEEKDAGEN_KORT[d.weekday()]} {d.day} {MAANDEN_KORT[d.month - 1]}'


def _asLabel(d: date) -> str:
    """Kort, voor onder een kolom; de weekdag staat in de tooltip."""
    return f'{d.day} {MAANDEN_KORT[d.month - 1]}'


def _plekNaam(plek: str) -> str:
    return plek.replace('_', ' ')


def _procent(deel, geheel):
    return round(100 * deel / geheel) if geheel else None


def _gemiddeldeTreffers(sessies) -> int | None:
    """Hoeveel procent van de antwoorden was meteen goed: vragen / pogingen."""
    vragen = sum(s.vragen or 0 for s in sessies if s.pogingen)
    pogingen = sum(s.pogingen or 0 for s in sessies if s.pogingen)
    return _procent(vragen, pogingen)


def _gerangschikt(teller: Counter, max_: int | None = None) -> list[dict]:
    rijen = [{'naam': k, 'aantal': v} for k, v in teller.most_common(max_)]
    hoogste = rijen[0]['aantal'] if rijen else 0
    for rij in rijen:
        rij['deel'] = rij['aantal'] / hoogste if hoogste else 0
    return rijen


def overzicht(periode: str = '30') -> dict:
    from .models import Gebruik

    dagen = PERIODES.get(periode, 30)
    vandaag = datetime.now(TIJDZONE).date()
    query = Gebruik.query
    if dagen:
        eersteDag = vandaag - timedelta(days=dagen - 1)
        beginUtc = datetime.combine(eersteDag, datetime.min.time(), TIJDZONE).astimezone(timezone.utc)
        query = query.filter(Gebruik.tijd >= beginUtc.replace(tzinfo=None))
    rijen = query.order_by(Gebruik.tijd).all()
    if not dagen:
        eersteDag = _lokaal(rijen[0].tijd).date() if rijen else vandaag

    per = defaultdict(list)
    for rij in rijen:
        rij.lokaal = _lokaal(rij.tijd)
        per[rij.soort].append(rij)
    bezoeken, gestart, klaar = per['bezoek'], per['oefenen_start'], per['oefenen_klaar']
    quizStart, quizKlaar, quizGemaakt = per['quiz_gestart'], per['quiz_klaar'], per['quiz_aangemaakt']

    # Per dag
    alleDagen = [eersteDag + timedelta(days=i) for i in range((vandaag - eersteDag).days + 1)]
    bezoekersPerDag = defaultdict(set)
    for b in bezoeken:
        if b.bezoeker:
            bezoekersPerDag[b.lokaal.date()].add(b.bezoeker)
    gestartPerDag = Counter(s.lokaal.date() for s in gestart)
    klaarPerDag = Counter(s.lokaal.date() for s in klaar)
    quizPerDag = Counter(q.lokaal.date() for q in quizStart)
    perDag = [{
        'datum': d.isoformat(), 'label': _asLabel(d), 'naam': _dagLabel(d),
        'bezoekers': len(bezoekersPerDag.get(d, ())),
        'weergaven': 0,
        'gestart': gestartPerDag.get(d, 0),
        'afgerond': min(klaarPerDag.get(d, 0), gestartPerDag.get(d, 0)),
        'quizzen': quizPerDag.get(d, 0),
    } for d in alleDagen]
    weergavenPerDag = Counter(b.lokaal.date() for b in bezoeken)
    for rij in perDag:
        rij['weergaven'] = weergavenPerDag.get(date.fromisoformat(rij['datum']), 0)
        rij['nietAfgerond'] = rij['gestart'] - rij['afgerond']

    # Weekdag en uur (paginaweergaven: dat is 'de site gebruiken')
    raster = [[0] * 24 for _ in range(7)]
    for b in bezoeken:
        raster[b.lokaal.weekday()][b.lokaal.hour] += 1
    perWeekdag = [{'label': WEEKDAGEN_KORT[i], 'naam': WEEKDAGEN[i], 'aantal': sum(raster[i])} for i in range(7)]
    perUur = [{'label': f'{u}', 'naam': f'{u}:00 – {u + 1}:00', 'aantal': sum(raster[d][u] for d in range(7))}
              for u in range(24)]
    hoogsteCel = max((max(r) for r in raster), default=0)
    heatmap = [{
        'dag': WEEKDAGEN_KORT[d], 'naam': WEEKDAGEN[d],
        'cellen': [{'uur': u, 'aantal': raster[d][u],
                    'stap': 0 if not raster[d][u] else min(5, 1 + int(5 * raster[d][u] / (hoogsteCel + 1)))}
                   for u in range(24)],
    } for d in range(7)]

    # Kaarten
    kaarten = []
    for kaart in sorted({s.kaart for s in gestart + klaar + quizStart if s.kaart}):
        g = [s for s in gestart if s.kaart == kaart]
        k = [s for s in klaar if s.kaart == kaart]
        kaarten.append({
            'naam': kaart, 'gestart': len(g), 'afgerond': len(k),
            'afgerondPct': _procent(min(len(k), len(g)), len(g)),
            'treffers': _gemiddeldeTreffers(k),
            'duur': round(statistics.median([s.duur for s in k if s.duur]) / 60, 1) if any(s.duur for s in k) else None,
            'quizzen': sum(1 for q in quizStart if q.kaart == kaart),
        })
    kaarten.sort(key=lambda r: (-r['gestart'], -r['quizzen'], r['naam']))
    hoogsteKaart = max((r['gestart'] for r in kaarten), default=0)
    for r in kaarten:
        r['deel'] = r['gestart'] / hoogsteKaart if hoogsteKaart else 0

    onderdelen = Counter()
    for s in gestart:
        for o in (s.onderdelen or '').split(','):
            if o:
                onderdelen[f'{o} ({s.kaart})'] += 1

    # Hoe ging het?
    trefferBakken = [('< 50%', 0, 50), ('50–69%', 50, 70), ('70–84%', 70, 85),
                     ('85–94%', 85, 95), ('95–100%', 95, 101)]
    treffers = [round(100 * s.vragen / s.pogingen) for s in klaar if s.pogingen and s.vragen]
    perTreffers = [{'label': naam, 'naam': naam, 'aantal': sum(1 for t in treffers if van <= t < tot)}
                   for naam, van, tot in trefferBakken]
    duurBakken = [('< 2 min', 0, 120), ('2–5 min', 120, 300), ('5–10 min', 300, 600),
                  ('10–20 min', 600, 1200), ('> 20 min', 1200, 10 ** 9)]
    duren = [s.duur for s in klaar if s.duur]
    perDuur = [{'label': naam, 'naam': naam, 'aantal': sum(1 for d in duren if van <= d < tot)}
               for naam, van, tot in duurBakken]

    moeilijk = defaultdict(lambda: {'keer': 0, 'extra': 0})
    for s in klaar:
        try:
            fout = json.loads(s.fout) if s.fout else {}
        except ValueError:
            fout = {}
        for plek, extra in fout.items():
            sleutel = (s.kaart, plek)
            moeilijk[sleutel]['keer'] += 1
            moeilijk[sleutel]['extra'] += int(extra)
    afgerondPerKaart = Counter(s.kaart for s in klaar)
    moeilijkst = sorted(({
        'plek': _plekNaam(plek), 'kaart': kaart, 'keer': v['keer'], 'extra': v['extra'],
        'pct': _procent(v['keer'], afgerondPerKaart.get(kaart, 0)),
    } for (kaart, plek), v in moeilijk.items()), key=lambda r: (-r['keer'], -r['extra'], r['plek']))[:15]
    hoogsteMoeilijk = moeilijkst[0]['keer'] if moeilijkst else 0
    for r in moeilijkst:
        r['deel'] = r['keer'] / hoogsteMoeilijk if hoogsteMoeilijk else 0

    # Wie en waarmee
    apparaten = Counter()
    for (dag, code), soort in {((b.lokaal.date(), b.bezoeker), b.apparaat) for b in bezoeken if b.bezoeker}:
        apparaten[soort or 'onbekend'] += 1

    bezoekersTotaal = sum(len(v) for v in bezoekersPerDag.values())
    plekken = plekOverzicht(bezoeken, gestart, eersteDag if dagen else None)
    return {
        'plekken': plekken,
        'periode': periode if periode in PERIODES else '30',
        'periodes': [('7', '7 dagen'), ('30', '30 dagen'), ('90', '90 dagen'), ('alles', 'Alles')],
        'van': _dagLabel(eersteDag), 'tot': _dagLabel(vandaag), 'aantalDagen': len(alleDagen),
        'leeg': not rijen,
        'tegels': {
            'bezoekers': bezoekersTotaal,
            'bezoekersPerDag': round(bezoekersTotaal / len(alleDagen), 1) if alleDagen else 0,
            'weergaven': len(bezoeken),
            'gestart': len(gestart),
            'afgerond': len(klaar),
            'afgerondPct': _procent(min(len(klaar), len(gestart)), len(gestart)),
            'treffers': _gemiddeldeTreffers(klaar),
            'duur': round(statistics.median(duren) / 60, 1) if duren else None,
            'quizzen': len(quizStart),
            'quizLeerlingen': sum(q.spelers or 0 for q in quizStart),
            'quizGemiddeld': round(statistics.mean([q.spelers for q in quizStart if q.spelers]), 1)
                             if any(q.spelers for q in quizStart) else None,
            'quizAfgemaakt': _procent(min(len(quizKlaar), len(quizStart)), len(quizStart)),
            'quizNietGestart': max(0, len(quizGemaakt) - len(quizStart)),
        },
        'perDag': perDag,
        'perWeekdag': perWeekdag,
        'perUur': perUur,
        'heatmap': heatmap,
        'drukstUur': max(perUur, key=lambda r: r['aantal']) if bezoeken else None,
        'drukstDag': max(perWeekdag, key=lambda r: r['aantal']) if bezoeken else None,
        'kaarten': kaarten,
        'vormen': _gerangschikt(Counter(s.vorm for s in gestart if s.vorm)),
        'onderdelen': _gerangschikt(onderdelen, 12),
        'niveaus': _gerangschikt(Counter(s.niveau for s in gestart if s.niveau)),
        'perTreffers': perTreffers,
        'perDuur': perDuur,
        'moeilijkst': moeilijkst,
        'apparaten': _gerangschikt(apparaten),
        'paginas': _gerangschikt(Counter(b.pagina for b in bezoeken)),
        'quizKaarten': _gerangschikt(Counter(q.kaart for q in quizStart if q.kaart)),
        'quizGrootte': [{'label': naam, 'naam': naam + ' leerlingen',
                         'aantal': sum(1 for q in quizStart if q.spelers and van <= q.spelers < tot)}
                        for naam, van, tot in [('1–5', 1, 6), ('6–15', 6, 16), ('16–25', 16, 26),
                                               ('26–35', 26, 36), ('> 35', 36, 10 ** 6)]],
    }


# Onder deze grens tonen we geen exact aantal, zodat een enkele leerling uit
# een kleine provincie niet herkenbaar is.
KLEIN = 5


def _toon(aantal: int) -> str:
    if aantal == 0:
        return '0'
    return f'< {KLEIN}' if aantal < KLEIN else str(aantal)


def _provincieStap(n: int, hoogste: int) -> int:
    """Kleurstap 0-5. Onder KLEIN altijd stap 1; daarboven logaritmisch, want
    meestal is er een provincie (die van de school) die veel groter is en dan
    zou de rest anders allemaal dezelfde lichte kleur krijgen."""
    if n == 0:
        return 0
    if n < KLEIN:
        return 1
    if hoogste <= KLEIN:
        return 5
    deel = math.log(n / KLEIN) / math.log(hoogste / KLEIN)
    return min(5, 2 + int(3.999 * deel))


def plekOverzicht(bezoeken, gestart, beginPeriode=None) -> dict:
    """Provincies en landen. Bezoekers = verschillende bezoekers per dag."""
    from . import locatie
    from .models import Gebruik, db

    perProvincie = defaultdict(set)
    perLand = defaultdict(set)
    school, elders, onbekend = set(), set(), set()
    for b in bezoeken:
        sleutel = (b.lokaal.date(), b.bezoeker)
        if not b.bezoeker:
            continue
        if b.school:
            school.add(sleutel)
            continue
        if b.school is False:
            elders.add(sleutel)
        if b.land == 'NL' and b.provincie:
            perProvincie[b.provincie].add(sleutel)
        elif b.land and b.land != 'NL':
            perLand[b.land].add(sleutel)
        else:
            onbekend.add(sleutel)
    sessiesPerProvincie = Counter(s.provincie for s in gestart if s.provincie and not s.school)

    # Wanneer kwam er voor het eerst iemand uit een provincie? Over alle tijd,
    # niet alleen de gekozen periode: zo zie je wanneer een provincie erbij kwam.
    eerste = {}
    try:
        for provincie, tijd in (db.session.query(Gebruik.provincie, db.func.min(Gebruik.tijd))
                                .filter(Gebruik.provincie.isnot(None))
                                .filter(db.or_(Gebruik.school.is_(None), Gebruik.school.is_(False)))
                                .group_by(Gebruik.provincie).all()):
            eerste[provincie] = _lokaal(tijd).date()
    except Exception:
        pass

    hoogste = max((len(v) for v in perProvincie.values()), default=0)
    vormen = locatie.provincieVormen()
    provincies = []
    for vorm in vormen['provincies']:
        naam = vorm['naam']
        n = len(perProvincie.get(naam, ()))
        stap = _provincieStap(n, hoogste)
        provincies.append({
            'naam': naam, 'paden': vorm['paden'], 'aantal': n, 'tekst': _toon(n), 'stap': stap,
            'sessies': sessiesPerProvincie.get(naam, 0), 'sessiesTekst': _toon(sessiesPerProvincie.get(naam, 0)),
            'eerste': _dagLabel(eerste[naam]) if naam in eerste else None,
            'eersteDatum': eerste[naam].isoformat() if naam in eerste else '',
            'nieuw': bool(naam in eerste and beginPeriode and eerste[naam] >= beginPeriode),
        })
    gerangschikt = sorted(provincies, key=lambda p: (-p['aantal'], p['naam']))

    landen = [{'naam': locatie.landNaam(code), 'aantal': len(v), 'tekst': _toon(len(v))}
              for code, v in perLand.items()]
    landen.sort(key=lambda r: (-r['aantal'], r['naam']))
    hoogsteLand = landen[0]['aantal'] if landen else 0
    for r in landen:
        r['deel'] = r['aantal'] / hoogsteLand if hoogsteLand else 0

    return {
        'beschikbaar': locatie.beschikbaar(),
        'schoolIngesteld': bool(locatie._schoolNetwerken()),
        'viewBox': vormen['viewBox'],
        'provincies': provincies,
        'gerangschikt': gerangschikt,
        'metBezoekers': sum(1 for p in provincies if p['aantal']),
        'landen': landen,
        'school': len(school), 'schoolTekst': _toon(len(school)),
        'elders': len(elders), 'eldersTekst': _toon(len(elders)),
        'onbekend': len(onbekend),
        'klein': KLEIN,
    }


# ----------------------------------------------------------------------
# Kolomgrafieken: de maten worden hier uitgerekend, de template tekent ze.
# ----------------------------------------------------------------------
def _mooiMaximum(hoogste: int) -> tuple[int, int]:
    """Een rond maximum en de stapgrootte voor de lijnen (hooguit 4 lijnen)."""
    if hoogste <= 0:
        return 4, 1
    stap = 1
    while True:
        for factor in (1, 2, 5):
            s = stap * factor
            if hoogste / s <= 4:
                return s * -(-hoogste // s), s
        stap *= 10


def kolommen(items: list[dict], waarden: list[str], breedte: int = 720, hoogte: int = 200,
             labelElke: int | None = None) -> dict:
    """Maten voor een (gestapelde) kolomgrafiek.

    `waarden` zijn de sleutels die op elkaar gestapeld worden, van onder naar
    boven. Kolommen zijn hooguit 24 pixels breed met 2 pixels lucht ertussen;
    alleen de bovenkant is afgerond.
    """
    links, onder, boven = 34, 26, 10
    plotB, plotH = breedte - links - 4, hoogte - onder - boven
    hoogste = max((sum(i.get(w, 0) for w in waarden) for i in items), default=0)
    maximum, stap = _mooiMaximum(hoogste)
    vak = plotB / max(1, len(items))
    kolomB = max(2, min(24, vak - 2))
    if labelElke is None:
        labelElke = max(1, -(-len(items) * 44 // plotB))   # labels van ~40px mogen elkaar niet raken
    kolomData = []
    for n, item in enumerate(items):
        x = links + n * vak + (vak - kolomB) / 2
        y = boven + plotH
        stukken = []
        aanwezig = [w for w in waarden if item.get(w, 0) > 0]
        for w in waarden:
            v = item.get(w, 0)
            if v <= 0:
                continue
            h = plotH * v / maximum
            bovenste = w == aanwezig[-1]
            gat = 0 if w == aanwezig[0] else 2       # 2px lucht tussen gestapelde stukken
            stukken.append({'sleutel': w, 'x': round(x, 1), 'y': round(y - h, 1),
                            'b': round(kolomB, 1), 'h': round(max(0, h - gat), 1), 'rond': bovenste})
            y -= h
        kolomData.append({
            'item': item, 'stukken': stukken,
            'vakX': round(links + n * vak, 1), 'vakB': round(vak, 1),
            'midden': round(x + kolomB / 2, 1),
            'label': item['label'] if n % labelElke == 0 else None,
        })
    lijnen = [{'y': round(boven + plotH - plotH * t / maximum, 1), 'tekst': f'{t:,}'.replace(',', '.')}
              for t in range(0, maximum + 1, stap)]
    return {'breedte': breedte, 'hoogte': hoogte, 'links': links, 'rechts': breedte - 4,
            'onder': boven + plotH, 'kolommen': kolomData, 'lijnen': lijnen}


def bovenkantPad(x: float, y: float, b: float, h: float, rond: bool) -> str:
    """Pad voor een kolom met 4px afgeronde bovenhoeken (onderkant recht)."""
    r = min(4, b / 2, h) if rond else 0
    return (f'M{x},{y + h} L{x},{y + r} Q{x},{y} {x + r},{y} L{x + b - r},{y} '
            f'Q{x + b},{y} {x + b},{y + r} L{x + b},{y + h} Z')
