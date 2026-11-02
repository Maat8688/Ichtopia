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

## Accounts

Oefenen kan zonder account; inloggen is optioneel.

- `/registreren` - account aanmaken. Wie "docent" kiest, moet de `KAHOOT_HOST_CODE`
  invullen; zo kunnen leerlingen zichzelf geen docentrechten geven.
- `/inloggen` - inloggen met e-mail en wachtwoord (`/login` stuurt hierheen door).
- `/account` - je gegevens en de uitlogknop.

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
MAX_PRACTICE_SESSIONS=400            # oefensessies tegelijk in het geheugen
PRACTICE_SESSION_IDLE_SECONDS=3600   # daarna verloopt een ongebruikte sessie
```

Een oefensessie met de wereldkaart kost een paar MB geheugen en iedereen kan er
een starten, dus er zit een maximum op (de langst niet gebruikte gaat eruit) en
per IP mogen er hooguit 200 per tien minuten bij. Dat is ruim voor een klas
achter een schoolnetwerk.

`src/monitor.py` leest `log/access.log` en stuurt alerts via ntfy of Discord.
Zet daarvoor `NTFY_TOPIC` en/of `DISCORD_WEBHOOK_URL` in `.env`; leeg is uit.

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
"admin". Het filter kijkt ook door l3etspeak en tussengevoegde tekens heen
("K-U-T", "K4nker"). Hetzelfde filter geldt voor accountnamen en voor de naam
waarmee een leerling aan een klassikale quiz meedoet.

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
en 1000 elo.

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
```
