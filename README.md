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

Omgevingsvariabelen:

```
DATABASE_URL=postgresql://gebruiker:wachtwoord@db:5432/main
COOKIE_SECURE=1   # alleen als er https voor de app zit; standaard uit
```

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

## Tests

Draaien vanuit `app`, allemaal op een tijdelijke SQLite-database:

```
python tests/test_names.py     # het naamfilter
python tests/test_auth.py      # registreren, inloggen, afgeschermde pagina's
python tests/test_ranking.py   # XP, levels, elo, ranglijst en een heel duel
```
