# AK-leer-website
 Een website om aardrijkskunde te leren in opdracht van het Ichthus Lyceum

## Klassikale quiz (Kahoot-modus)

Docenten hosten een quiz via `/host`, leerlingen doen mee via `/join` met een pincode.
De docentpagina is afgeschermd met een docentcode. Zet in `app/.env`:

```
SECRET_KEY=een-lange-willekeurige-string
KAHOOT_HOST_CODE=de-code-die-alleen-docenten-kennen
```

Zonder `KAHOOT_HOST_CODE` kan niemand een quiz hosten. Oude accounts met
`account_type = TEACHER` mogen nog zonder code hosten; nieuwe docentaccounts
kun je niet meer aanmaken.

## Accounts

Oefenen kan zonder account; inloggen is optioneel.

- `/registreren` - account aanmaken. Er is geen keuze tussen leerling en docent:
  iedereen krijgt hetzelfde account. Docenten starten een klassikale quiz met
  de `KAHOOT_HOST_CODE` op `/host`, dus een leerling kan zichzelf nooit
  docentrechten geven.
- `/inloggen` - inloggen met je naam en wachtwoord (`/login` stuurt hierheen door).
  Hoofdletters maken bij de naam niet uit.
- `/account` - je gegevens en de uitlogknop.

Er wordt geen e-mailadres gevraagd of bewaard: we hebben er niets aan en het is
een persoonsgegeven van een kind. Dat betekent ook dat er geen "wachtwoord
vergeten" is. Wie zijn wachtwoord kwijt is, maakt een nieuw account aan.
Bestaande e-mailadressen worden gewist door de migratie `e2b4c6d8f0a1` en, als
die nog niet gedraaid is, ook bij het opstarten van de app.

Wachtwoorden staan als hash in de database (werkzeug, scrypt). Formulieren zijn
beveiligd met een CSRF-token en na vijf mislukte inlogpogingen is een IP-adres
vijf minuten geblokkeerd.

## Online zetten

`docker compose up -d --build` start drie containers:

- **caddy** - het enige wat van buiten bereikbaar is (poort 80 en 443). Regelt
  https met een certificaat van Let's Encrypt en stuurt door naar de app.
- **web** - de app onder gunicorn (een worker, 100 threads). Een worker is
  bewust: quizzen, duels en oefensessies staan in het geheugen van dat proces.
- **db** - Postgres, alleen bereikbaar voor de app (geen open poort).

Kopieer `app/.env.example` naar `app/.env` en vul alles in. Zet `DOMAIN` op de
echte domeinnaam; die moet in DNS al naar de server wijzen en poort 80 en 443
moeten open staan, anders krijgt Caddy geen certificaat.

`.env` gaat niet mee in de Docker-image; compose geeft de waarden bij het
starten door. Zet hem dus ook nooit in git.

Andere instellingen (in docker-compose al goed gezet):

```
COOKIE_SECURE=1   # cookies alleen over https; lokaal zonder https: 0
TRUST_PROXY=1     # echte IP van bezoekers uit X-Forwarded-For van Caddy halen.
                  # Alleen aanzetten als er echt een proxy voor zit, anders kan
                  # iedereen zijn IP verzinnen en om de inlogrem heen.
MAX_PRACTICE_SESSIONS=250            # oefensessies tegelijk in het geheugen
PRACTICE_SESSION_IDLE_SECONDS=10800  # daarna (3 uur) verloopt een ongebruikte sessie
SCHOOL_NETWERK=                      # IP van de school, voor /statistieken (zie daar)
```

Een oefensessie met de wereldkaart kost een paar MB geheugen en iedereen kan er
een starten, dus er zit een maximum op (de langst niet gebruikte gaat eruit) en
per IP mogen er hooguit 200 per tien minuten bij. Dat is ruim voor een klas
achter een schoolnetwerk.

`src/monitor.py` leest `log/access.log` en stuurt alerts via ntfy of Discord.
Zet daarvoor `NTFY_TOPIC` en/of `DISCORD_WEBHOOK_URL` in `.env`; leeg is uit.

## Toetsmodus

Op de startpagina kies je onder de vraagvorm **Oefenen** of **Toets**. Bij een
toets kies je het aantal vragen (10, 20, 30 of alle). Dan:

- komt elke vraag precies een keer, in willekeurige volgorde;
- hoor je tussendoor niet of het goed was, en kleurt de kaart niet in;
- krijg je aan het eind een cijfer: 1 + 9 × (goed / totaal), op een decimaal,
  met een lijst van wat je fout had (het goede antwoord en wat jij gaf). Pas
  dan kleurt de kaart in;
- krijg je XP als je ingelogd bent, net als bij oefenen.

Werkt met alle drie de vraagvormen. Op `/statistieken` staan toetsen apart:
aantal, gemiddeld cijfer en hoeveel er voldoende waren. Ze tellen niet mee bij
het gewone oefenen.

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

`test_locatie.py` heeft `pip install mmdb-writer` nodig.

## Punten, levels en duels

Twee losse ladders, allebei zichtbaar op `/ranglijst`:

- **XP en levels** verdien je door te oefenen, mee te doen met een klassikale
  quiz of een duel te spelen. XP kan alleen omhoog. Er zit een rem van 600 XP
  per dag op, zodat dezelfde kleine kaart eindeloos herhalen niets oplevert.
- **Elo** verandert alleen door duels en kan ook zakken. Iedereen begint op
  1000. De eerste tien duels tellen zwaarder mee (K=40, daarna K=24).

Een duel (`/duel`) is 1 tegen 1: allebei dezelfde vragen tegelijk, sneller goed
antwoorden levert meer punten op, de winnaar pakt elo van de ander af. Je maakt
een duel aan en deelt de code, of je pakt er een uit de lijst met openstaande
duels.

Elo is nul-som: om de beurt winnen levert allebei niets op, dus daar hoeft geen
rem op. Wat wel misbruikt kan worden is eenzijdig voeren - iemand die zich
steeds expres laat verliezen, of een tweede account dat alleen bestaat om
punten weg te geven. Daarom tellen alleen je eerste drie overwinningen per dag
op dezelfde tegenstander mee voor de elo. Verlies en gelijkspel tellen altijd,
en de teller staat per richting, dus twee rivalen die de hele middag tegen
elkaar spelen en netjes wisselen merken hier niets van.

## Namen

Namen komen op de ranglijst, op het digibord en in duels te staan, dus ze gaan
door een filter (`src/names.py`): 2 tot 20 tekens, alleen letters, cijfers,
spaties, punten en streepjes, en geen scheldwoorden of namen als "docent" of
"admin". Het filter kijkt door de trucs heen die bruggers proberen:

- leetspeak en tekens ertussen: "H1tl3r", "k@nk3r", "K-U-T", "k a n k e r";
- letters herhalen ("kaaaanker"), klankspelling ("phuck", "fvck") en
  achterstevoren ("reltih");
- letters uit andere alfabetten die er hetzelfde uitzien (Cyrillische а, о, е);
- getallen als 1488, 69 en 420;
- rare namen: toetsenbordrijen ("qwerty", "asdf"), woorden zonder klinkers,
  drie keer dezelfde letter, meer dan vier cijfers, @-handles en websites.

Echte namen die toevallig op een scheldwoord lijken (Nazir, Kutlu, Lulof, Isis)
staan in `TOEGESTAAN` en mogen wel. Een naam die te veel lijkt op een bestaand
account ("F1oris" als "Floris" al bestaat) wordt ook geweigerd, zodat niemand
zich voor een ander kan uitgeven.

Hetzelfde filter geldt voor accountnamen en voor de naam waarmee een leerling
aan een klassikale quiz meedoet.

De woordenlijst staat bovenin `src/names.py` en is bedoeld om aangevuld te
worden zodra er iets doorheen glipt.

## Een bestaande database bijwerken

De app maakt ontbrekende tabellen zelf aan bij het opstarten (`db.create_all()`),
maar voegt geen kolommen toe aan een tabel die al bestaat. Draait er al een
database van voor deze versie, dan moet je dus een keer migreren:

```
docker compose exec web flask db upgrade
```

Dat mag altijd en zo vaak je wilt: de migraties kijken eerst wat er al staat en
slaan over wat er al is. Bestaande accounts blijven staan en beginnen op 0 XP
en 1000 elo. De laatste migratie wist alle opgeslagen e-mailadressen.

Bij een lege database (of na `docker compose down -v`) hoeft dit niet.

> De drie oudste migraties zijn met opzet leeggemaakt. Alembic had daar ooit
> `op.drop_table('user')` van gemaakt, en die stonden klaar om alle accounts te
> wissen bij de eerste `flask db upgrade` op een database zonder
> alembic-geschiedenis.

## Tests

Draaien vanuit `app`, allemaal op een tijdelijke SQLite-database:

```
python tests/test_names.py       # het naamfilter
python tests/test_auth.py        # registreren, inloggen, afgeschermde pagina's
python tests/test_ranking.py     # XP, levels, elo, ranglijst en een heel duel
python tests/test_migraties.py   # upgrade op een oude en op een verse database
python tests/test_security.py    # sessiegrenzen, rem, csrf, X-Forwarded-For
python tests/test_kaart.py       # kaarten inlezen: land blijft land
python tests/test_toets.py       # de toetsmodus en het cijfer
python tests/test_statistieken.py  # /statistieken en wat er geteld wordt
python tests/test_bots.py        # bots herkennen
python tests/test_locatie.py     # provincie bij een IP (heeft mmdb-writer nodig)
```
