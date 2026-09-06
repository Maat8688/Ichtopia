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

De rooktest van het accountsysteem draai je vanuit `app` met
`python tests/test_auth.py` (gebruikt een tijdelijke SQLite-database).
