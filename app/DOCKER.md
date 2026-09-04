# Running the stack

```
cd app
cp .env.example .env      # first time only, then fill it in
docker compose up --build
```

> **De database staat uit.** De app draait zonder Postgres: het spel houdt
> zijn state in het geheugen en niets raakt nog een database aan. De
> `db`-service is uit `docker-compose.yaml` verwijderd en de code staat
> uitgecommentarieerd in `src/__init__.py` en `src/routes.py`.
> Alles hieronder geldt alleen als je de database weer aanzet.

## The two things that bite

The `postgres_data` volume outlives the config that created it. Two settings
must keep matching what is already inside that volume, and Postgres will not
adapt either of them for you.

### 1. Major version

The `db` image tag must match the major version that initialised the volume.
Symptom:

```
FATAL:  database files are incompatible with server
DETAIL:  The data directory was initialized by PostgreSQL version 17,
         which is not compatible with this version 16.x
```

Fix: set the image back to the major version named in `DETAIL`. Downgrading a
data directory is not possible in place; going the other way (16 to 17) needs
`pg_dumpall` and a reload, not just a new tag.

Check what a volume holds without starting anything:

```
docker run --rm -v app_postgres_data:/d alpine cat /d/PG_VERSION
```

### 2. Role and password

`POSTGRES_USER` and `POSTGRES_PASSWORD` create a role **only when the volume is
empty**. On an existing volume the database ignores them, but `web` still
builds `DATABASE_URL` out of them. If they drift apart:

```
FATAL:  password authentication failed for user "postgres"
DETAIL:  Role "postgres" does not exist.
```

That `DETAIL` line is the tell. The role your `.env` asks for is simply not in
the cluster.

#### Find the role that does exist

Local socket connections inside the container are trusted, but `psql` still
needs a role name to connect with. Read the names straight out of the shared
catalog instead:

```
docker compose up -d db
docker compose exec -u postgres db sh -c \
  "cat /var/lib/postgresql/data/global/* 2>/dev/null | tr -c '[:print:]' '\n' \
   | grep -Ex '[a-zA-Z_][a-zA-Z0-9_-]{2,63}' | sort -u"
```

Among database names (`main`, `template0`, `template1`) and SCRAM hashes you
will see the role names. The authoritative version, with the server stopped:

```
docker compose stop db
docker compose run --rm --user postgres --entrypoint sh db -c \
  "echo 'SELECT rolname FROM pg_authid;' | postgres --single -D /var/lib/postgresql/data main"
```

#### Then reconcile

Preferred, because it keeps the role that owns the existing tables. Put that
role name in `.env` as `POSTGRES_USER`, then reset its password to match
`POSTGRES_PASSWORD` (the local socket needs no password):

```
docker compose up -d db
docker compose exec -u postgres db \
  psql -U <real_role> -d main -c "ALTER ROLE <real_role> WITH PASSWORD '<pw from .env>';"
docker compose up -d web
```

Alternative, if you would rather keep `.env` as it is, add the role it expects:

```
docker compose exec -u postgres db \
  psql -U <real_role> -d main -c "CREATE ROLE postgres LOGIN SUPERUSER PASSWORD '<pw from .env>';"
```

## Before you reach for `down -v`

`docker compose down -v` deletes the volume and every row in it. It makes the
errors above disappear because the cluster is rebuilt from your current `.env`,
which is exactly why it is tempting and exactly why it is dangerous. Take a
dump first:

```
docker compose exec -u postgres db pg_dumpall -U <real_role> > backup-$(date +%F).sql
```

Also confirm you are even looking at the right volume. The name is derived from
the compose project, which defaults to the directory name, so running from a
different directory silently points at a different database:

```
docker volume ls | grep postgres
```
