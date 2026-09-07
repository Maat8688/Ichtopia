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
