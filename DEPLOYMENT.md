# Docker, Ubuntu, and Azure deployment

The repository provides a three-service Docker Compose setup for local development and Ubuntu, plus separate Terraform and Ansible automation for Azure. PostgreSQL stores application records in its own persistent volume. The frontend and API build as independent images.

## Start the local application

Copy `.env.example` to `.env`, set independent random values for `APP_SECRET` and `POSTGRES_PASSWORD`, and retain the default loopback-only PostgreSQL port.

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8080/api/health
```

Open **http://localhost:8080**. PostgreSQL listens on loopback port 5433 by default. Nginx is published on port 8080. The API reaches PostgreSQL on the private Compose network.

## Build and transfer images

Build the frontend and API images independently with `docker compose build frontend backend`. To transfer them, save each image with `docker image save`, load it on the target Linux Docker host, and start the Compose file with `docker compose up -d --no-build`. Keep the destination `.env` and the PostgreSQL data volume separate from image archives.

## Ubuntu

Use the self-contained [Ubuntu deployment package](ubuntu-deploy/README.md). It includes the backend, frontend, Compose configuration, and PostgreSQL schema.

## Database backups

Make PostgreSQL logical backups with `pg_dump` and restore them with `pg_restore` into a fresh database. Preserve the `postgres-data` volume and the signing secret when upgrading a host installation.

## Azure CI/CD

Follow the [Jenkins, Terraform and Ansible guide](infra/README.md) to configure remote Terraform state, Jenkins credentials, container registry access, Azure identity, and deployment.
