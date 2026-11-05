"""Uit welke provincie (of welk land) komt een bezoeker?

Het IP-adres wordt hier opgezocht in een database die op de server zelf staat
(DB-IP 'IP to City Lite', gratis, CC BY 4.0). Er gaat dus niets naar een
andere dienst. Het adres zelf wordt nergens bewaard: wat in de tabel gebruik
komt is alleen het land en de provincie.

Hoe nauwkeurig: het land klopt bijna altijd, de provincie meestal bij
thuisinternet. Mobiel internet komt vaak uit bij de provider (Noord-Holland),
en iedereen op het schoolnetwerk komt uit op dezelfde plek. Zet daarom het
netwerk van de school in SCHOOL_NETWERK; die bezoeken worden dan als 'op
school' geteld in plaats van als een provincie.

De database ophalen of bijwerken: python geo_bijwerken.py (elke maand een
nieuwe versie).
"""
from __future__ import annotations

import ipaddress
import os
import threading

GEO_DB = os.getenv('GEO_DB', os.path.join('data', 'geo', 'dbip-city-lite.mmdb'))

# Provincies: naam op de site -> id in data/maps/Nederland.svg.
PROVINCIES = {
    'Groningen': 'Groningen',
    'Friesland': 'Friesland',
    'Drenthe': 'Drenthe',
    'Overijssel': 'Overijsel',
    'Flevoland': 'Flevoland',
    'Gelderland': 'Gelderland',
    'Utrecht': 'Utrecht',
    'Noord-Holland': 'Noord-Holland',
    'Zuid-Holland': 'Zuid-Holland',
    'Zeeland': 'Zeeland',
    'Noord-Brabant': 'Noord-Brabant',
    'Limburg': 'Limburg',
}

# Hoe de database een provincie kan noemen: Engels, Nederlands, Fries of als code.
_ALIASSEN = {
    'groningen': 'Groningen', 'nl-gr': 'Groningen', 'gr': 'Groningen',
    'friesland': 'Friesland', 'fryslân': 'Friesland', 'fryslan': 'Friesland', 'frisia': 'Friesland',
    'nl-fr': 'Friesland', 'fr': 'Friesland',
    'drenthe': 'Drenthe', 'nl-dr': 'Drenthe', 'dr': 'Drenthe',
    'overijssel': 'Overijssel', 'nl-ov': 'Overijssel', 'ov': 'Overijssel',
    'flevoland': 'Flevoland', 'nl-fl': 'Flevoland', 'fl': 'Flevoland',
    'gelderland': 'Gelderland', 'guelders': 'Gelderland', 'nl-ge': 'Gelderland', 'ge': 'Gelderland',
    'utrecht': 'Utrecht', 'nl-ut': 'Utrecht', 'ut': 'Utrecht',
    'north holland': 'Noord-Holland', 'noord-holland': 'Noord-Holland', 'noord holland': 'Noord-Holland',
    'nl-nh': 'Noord-Holland', 'nh': 'Noord-Holland',
    'south holland': 'Zuid-Holland', 'zuid-holland': 'Zuid-Holland', 'zuid holland': 'Zuid-Holland',
    'nl-zh': 'Zuid-Holland', 'zh': 'Zuid-Holland',
    'zeeland': 'Zeeland', 'zealand': 'Zeeland', 'nl-ze': 'Zeeland', 'ze': 'Zeeland',
    'north brabant': 'Noord-Brabant', 'noord-brabant': 'Noord-Brabant', 'noord brabant': 'Noord-Brabant',
    'nl-nb': 'Noord-Brabant', 'nb': 'Noord-Brabant',
    'limburg': 'Limburg', 'nl-li': 'Limburg', 'li': 'Limburg',
}

LANDEN = {
    'NL': 'Nederland', 'BE': 'België', 'DE': 'Duitsland', 'FR': 'Frankrijk', 'GB': 'Verenigd Koninkrijk',
    'ES': 'Spanje', 'IT': 'Italië', 'PT': 'Portugal', 'AT': 'Oostenrijk', 'CH': 'Zwitserland',
    'LU': 'Luxemburg', 'DK': 'Denemarken', 'SE': 'Zweden', 'NO': 'Noorwegen', 'FI': 'Finland',
    'PL': 'Polen', 'IE': 'Ierland', 'GR': 'Griekenland', 'TR': 'Turkije', 'MA': 'Marokko',
    'SR': 'Suriname', 'CW': 'Curaçao', 'AW': 'Aruba', 'BQ': 'Caribisch Nederland', 'SX': 'Sint Maarten',
    'US': 'Verenigde Staten', 'CA': 'Canada', 'ID': 'Indonesië', 'IN': 'India', 'CN': 'China',
}

_lezer = {'pad': None, 'mtime': None, 'db': None}
_lezerLock = threading.Lock()


def _database():
    """De database openen, en opnieuw openen als hij is bijgewerkt."""
    try:
        mtime = os.path.getmtime(GEO_DB)
    except OSError:
        return None
    with _lezerLock:
        if _lezer['db'] is None or _lezer['mtime'] != mtime or _lezer['pad'] != GEO_DB:
            try:
                import maxminddb
                oud = _lezer['db']
                _lezer['db'] = maxminddb.open_database(GEO_DB)
                _lezer['mtime'], _lezer['pad'] = mtime, GEO_DB
                if oud is not None:
                    oud.close()
            except Exception:
                _lezer['db'] = None
                return None
        return _lezer['db']


def beschikbaar() -> bool:
    return _database() is not None


def _schoolNetwerken():
    netwerken = []
    for stuk in os.getenv('SCHOOL_NETWERK', '').split(','):
        stuk = stuk.strip()
        if stuk:
            try:
                netwerken.append(ipaddress.ip_network(stuk, strict=False))
            except ValueError:
                pass
    return netwerken


def opSchool(ip: str | None) -> bool | None:
    """True/False als SCHOOL_NETWERK is ingesteld, anders None (weten we niet)."""
    netwerken = _schoolNetwerken()
    if not netwerken or not ip:
        return None
    try:
        adres = ipaddress.ip_address(ip)
    except ValueError:
        return None
    return any(adres in netwerk for netwerk in netwerken)


def _provincieUit(record: dict) -> str | None:
    for deel in record.get('subdivisions') or []:
        kandidaten = [deel.get('iso_code')] + list((deel.get('names') or {}).values())
        for naam in kandidaten:
            if naam and naam.strip().lower() in _ALIASSEN:
                return _ALIASSEN[naam.strip().lower()]
    return None


def zoekOp(ip: str | None) -> tuple[str | None, str | None]:
    """(landcode, provincie) bij een IP-adres. Provincie alleen in Nederland.

    Geeft (None, None) als het niet te zeggen is: geen database, een intern
    adres (zoals 127.0.0.1 of het netwerk thuis) of een onbekend adres."""
    if not ip:
        return None, None
    try:
        adres = ipaddress.ip_address(ip)
    except ValueError:
        return None, None
    if adres.is_private or adres.is_loopback or adres.is_reserved:
        return None, None
    db = _database()
    if db is None:
        return None, None
    try:
        record = db.get(str(adres)) or {}
    except Exception:
        return None, None
    land = ((record.get('country') or {}).get('iso_code') or None)
    provincie = _provincieUit(record) if land == 'NL' else None
    return land, provincie


def landNaam(code: str | None) -> str:
    if not code:
        return 'onbekend'
    return LANDEN.get(code, code)


# ----------------------------------------------------------------------
# De provincies als vormen, voor de kaart op /statistieken
# ----------------------------------------------------------------------
_vormen = {}


def provincieVormen() -> dict:
    """De twaalf provincies uit data/maps/Nederland.svg, zonder de rest van
    de kaart. Wordt een keer ingelezen en daarna onthouden."""
    if not _vormen:
        from bs4 import BeautifulSoup
        with open(os.path.join('data', 'maps', 'Nederland.svg'), encoding='utf-8') as f:
            svg = BeautifulSoup(f.read(), 'xml')
        perId = {}
        for g in svg.find_all('g', attrs={'category': 'Provincies'}):
            paden = []
            for pad in g.find_all('path'):
                pad.attrs.pop('style', None)
                pad.attrs.pop('id', None)
                paden.append(str(pad))
            perId[g.get('id')] = ''.join(paden)
        _vormen['viewBox'] = svg.find('svg').get('viewBox') or '0 0 1000 1000'
        _vormen['provincies'] = [{'naam': naam, 'paden': perId.get(svgId, '')}
                                 for naam, svgId in PROVINCIES.items()]
    return _vormen
