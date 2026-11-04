# AK-leer-website
 Een website om aardrijkskunde te leren in opdracht van het Ichthus Lyceum

## Klassikale quiz (Kahoot-modus)

Docenten hosten een quiz via `/host`, leerlingen doen mee via `/join` met een pincode.
De docentpagina is afgeschermd met een docentcode. Zet in `app/.env`:

```
SECRET_KEY=een-lange-willekeurige-string
KAHOOT_HOST_CODE=de-code-die-alleen-docenten-kennen
```

Zonder `KAHOOT_HOST_CODE` kan niemand een quiz hosten. Een ingelogd account met
`account_type = TEACHER` mag ook zonder code hosten.

## Op de server zetten (domeinnaam en https)

Voor de site staat Caddy. Die vraagt het certificaat bij Let's Encrypt aan,
stuurt http door naar https en vernieuwt het certificaat vanzelf. Alleen Caddy
is van buiten bereikbaar; de app en de database zitten erachter.

1. Laat de domeinnaam naar het adres van de server wijzen (een A-record).
   Controleer dat met `dig +short jouw-domein.nl` &mdash; daar moet het adres
   van de server uit komen. Zolang dat niet klopt, mislukt de aanvraag van het
   certificaat.
2. Zet je domeinnaam in `app/Caddyfile`, op de eerste regel, in plaats van
   `JOUW-DOMEIN.NL`.
3. Zorg dat `app/.env` deze regels heeft:

   ```
   SECRET_KEY=een-lange-willekeurige-string
   KAHOOT_HOST_CODE=de-code-die-alleen-docenten-kennen
   POSTGRES_USER=...
   POSTGRES_PASSWORD=...
   ```

4. Starten:

   ```
   cd app
   docker compose up -d
   docker compose logs -f caddy
   ```

   In die logs zie je of het certificaat gelukt is. Poort 80 en 443 moeten van
   buiten open staan: Let's Encrypt controleert via poort 80 of de server echt
   bij de domeinnaam hoort.

## Hoe de site draait

Voor de app staat Caddy (https), daarachter draait Gunicorn met de Flask-app,
en daarnaast Postgres. Zie `app/docker-compose.yaml`.

Gunicorn draait met **een enkele worker** en veel threads. Dat is geen
zuinigheid: de oefensessies en de lopende klassikale quizzen staan in het
geheugen van het proces. Met twee workers zou een leerling de ene keer bij
zijn eigen quiz uitkomen en de andere keer bij een leeg proces.

Meer mensen tegelijk gaat dus via `--threads`, niet via `--workers`. Elke
open verbinding bezet een thread, dus dat getal is het maximum aantal
deelnemers dat tegelijk kan meedoen. Gemeten: 70 leerlingen tegelijk in een
quiz kost ongeveer 85 MB.

Wil je ooit wel meerdere workers, dan moet die gedeelde toestand eerst naar
buiten het proces (Redis of de database).

## Statistieken

`/statistieken` (alleen met de docentcode) laat zien wie er nu bezig is, en
daaronder hoe de site de afgelopen 7, 30 of 90 dagen of sinds het begin is
gebruikt: bezoekers per dag, per dag van de week en per uur, een
warmtekaart van de week, welke kaarten, vraagvormen, onderdelen en niveaus,
hoeveel er meteen goed was, hoe lang een sessie duurt, de moeilijkste
plekken, de klassikale quizzen en welke apparaten. Elke grafiek is ook als
tabel te openen. Dezelfde cijfers staan in `/statistieken.json`.

Wat er wordt bijgehouden staat in de tabel `gebruik` (`src/models.py`,
vastgelegd en opgeteld in `src/gebruik.py`). Er gaan geen namen,
e-mailadressen of IP-adressen in. Om verschillende bezoekers op een dag te
kunnen tellen krijgt iedereen per dag een code, gemaakt met een geheim dat
elke dag nieuw is en alleen in het geheugen staat; morgen, en na een
herstart, is dezelfde leerling niet meer te herkennen. De tabel wordt bij het
opstarten vanzelf aangemaakt, en het tellen begint vanaf dat moment: van de
tijd daarvoor is niets bewaard.

### Provincies

Op `/statistieken` staat ook een kaart met de provincies waar bezoekers
vandaan komen, met per provincie de datum van het eerste bezoek. Zo zie je
wanneer er leerlingen uit een nieuwe provincie bij komen.

De provincie wordt bij elk bezoek opgezocht in een database die op de server
zelf staat (DB-IP 'IP to City Lite', gratis, CC BY 4.0). Het IP-adres wordt
daarna weggegooid; in de tabel komen alleen land en provincie. Aantallen onder
de 5 staan op de pagina als '< 5'.

De database ophalen, en daarna elke maand opnieuw (herstarten hoeft niet):

```
docker compose exec web python geo_bijwerken.py
```

Iedereen op het schoolnetwerk komt uit op één provincie. Zet daarom het
IP-adres van de school in `.env`, dan tellen die bezoeken apart:

```
SCHOOL_NETWERK=145.97.12.34
```

Meerdere adressen of reeksen mogen, met komma's: `145.97.12.0/24,2001:db8::/48`.
Het adres van de school vind je door op school naar bijvoorbeeld
https://ifconfig.me te gaan.

### Bots

Bovenaan `/statistieken` staat een knop **Bots: Weglaten / Meenemen**.
Standaard worden bots weggelaten. Als bot telt (`botReden()` in
`src/gebruik.py`):

- een bezoeker die zichzelf een bot noemt in de browsernaam: zoekmachines,
  AI-crawlers, linkvoorbeelden (WhatsApp, Discord), SEO-crawlers,
  monitoringdiensten, headless browsers en scripts (curl, Python);
- een browser die geen taal meestuurt (echte browsers doen dat altijd);
- meer dan 40 pagina's in één minuut van dezelfde bezoeker. Het
  schoolnetwerk telt daarvoor niet mee.

De reden staat bij elk bezoek in de kolom `bot`; onderaan de pagina staat
per reden hoeveel pagina's er werden weggelaten. Bezoeken van voor deze
versie zijn alleen aan de snelheid te herkennen.

Testen: `python tests/test_statistieken.py`, `python tests/test_locatie.py`
en `python tests/test_bots.py` (vanuit `app`; `test_locatie.py` heeft `pip install mmdb-writer` nodig).
