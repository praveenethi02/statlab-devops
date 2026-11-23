# Local and Ubuntu setup

The application uses PostgreSQL. Docker Compose provides the frontend, API, and database for local development.

## Run locally with Docker Compose

Copy `.env.example` to `.env`, set separate values for `APP_SECRET` and `POSTGRES_PASSWORD`, then start the services:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8080/api/health
```

Open **http://localhost:8080**. PostgreSQL is published on loopback port 5433 by default and persists data in the `postgres-data` volume. Keep `.env` and database backups out of Git.

## Run the API directly

Start the Compose database, set `DATABASE_URL` and `APP_SECRET` as described in the README, then run `python server.py`. Tests use the PostgreSQL database named by `DATABASE_URL` and create temporary schemas for isolation.

## Ubuntu package

The self-contained [Ubuntu deployment package](ubuntu-deploy/README.md) includes separate frontend and backend build contexts, Compose configuration, and the PostgreSQL schema.

## Database backups

Use `pg_dump` to create logical PostgreSQL backups and restore them into a fresh database with `pg_restore`. Plan any transfer from an existing SQLite installation separately before replacing a live system.
