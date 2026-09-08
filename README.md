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
