"""Haal de locatiedatabase op (of werk hem bij) voor de provincies op /statistieken.

    docker compose exec web python geo_bijwerken.py

Downloadt 'IP to City Lite' van DB-IP: gratis, zonder account, licentie
CC BY 4.0 (daarom staat er op /statistieken een vermelding van DB-IP). Er
komt elke maand een nieuwe versie; draai dit script dus maandelijks, met de
hand of met cron op de server:

    15 4 3 * *  cd /root/Ichtopia/app && docker compose exec -T web python geo_bijwerken.py

De app ziet een nieuwe versie vanzelf, herstarten hoeft niet. Het bestand
komt in data/geo/ (ongeveer 130 MB) en hoort niet in git.
"""
import gzip
import os
import shutil
import sys
import tempfile
import urllib.request
from datetime import date

HIER = os.path.dirname(os.path.abspath(__file__))
DOEL = os.getenv('GEO_DB') or os.path.join(HIER, 'data', 'geo', 'dbip-city-lite.mmdb')
ADRES = 'https://download.db-ip.com/free/dbip-city-lite-{maand}.mmdb.gz'


def maanden():
    """Deze maand, en anders de vorige (de nieuwe staat er soms pas na een paar dagen)."""
    vandaag = date.today()
    yield f'{vandaag:%Y-%m}'
    vorige = date(vandaag.year - (vandaag.month == 1), (vandaag.month - 2) % 12 + 1, 1)
    yield f'{vorige:%Y-%m}'


def main() -> int:
    os.makedirs(os.path.dirname(DOEL), exist_ok=True)
    for maand in maanden():
        url = ADRES.format(maand=maand)
        print(f'Ophalen: {url}')
        try:
            # Zonder eigen naam stuurt Python 'Python-urllib/3.x' mee, en dat
            # weigert de server van DB-IP (403).
            verzoek = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; Ichtopia-geo-bijwerken/1.0; +https://ichtopia.nl)',
                'Accept': '*/*',
            })
            with urllib.request.urlopen(verzoek, timeout=120) as antwoord:
                with tempfile.NamedTemporaryFile(dir=os.path.dirname(DOEL), delete=False) as tijdelijk:
                    with gzip.GzipFile(fileobj=antwoord) as uitgepakt:
                        shutil.copyfileobj(uitgepakt, tijdelijk)
        except Exception as fout:
            print(f'  lukt niet ({fout})')
            continue

        # Eerst controleren dat het een bruikbare database is, dan pas vervangen.
        try:
            import maxminddb
            with maxminddb.open_database(tijdelijk.name) as db:
                soort = db.metadata().database_type
        except Exception as fout:
            os.unlink(tijdelijk.name)
            print(f'  geen geldige database ({fout})')
            return 1
        os.replace(tijdelijk.name, DOEL)
        print(f'Klaar: {DOEL} ({soort}, {os.path.getsize(DOEL) // 1_000_000} MB, versie {maand})')
        return 0
    print('Niet gelukt. Probeer het later nog eens, of kijk op https://db-ip.com/db/download/ip-to-city-lite')
    return 1


if __name__ == '__main__':
    sys.exit(main())
