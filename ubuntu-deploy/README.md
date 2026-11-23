# StatLab three-tier deployment for Ubuntu

This folder is a self-contained deployment package. Transfer it to Ubuntu or generate the ZIP with `python scripts/prepare_ubuntu.py` from the project root. It includes separate frontend and backend build contexts and the PostgreSQL schema.

```text
ubuntu-deploy/
  frontend/       Nginx image, website assets, and API proxy
  backend/        Python API image and PostgreSQL migrations
  compose.yaml    Frontend, API, and PostgreSQL services
  .env.example    Runtime settings
  setup_env.py    Creates a fresh secret configuration
```

## Start on Ubuntu

Install Docker Engine and the Compose plugin. Run these commands from this folder.

```bash
python3 setup_env.py --host YOUR_UBUNTU_SERVER_IP
docker compose up -d --build --wait --wait-timeout 120
docker compose ps
curl --fail http://localhost:8080/api/health
```

The setup script writes a random `APP_SECRET` and `POSTGRES_PASSWORD`, plus the allowed host names. It refuses to overwrite an existing `.env`. Open **http://YOUR_UBUNTU_SERVER_IP:8080**. Permit that HTTP port through the host or network firewall. The supplied setup is for a trusted network. Configure HTTPS before exposing the site publicly.

Nginx serves the frontend and forwards `/api/` to the backend over the private Compose network. PostgreSQL has its own persistent `postgres-data` volume and is published only on the server's loopback interface for local administration. The API alone connects to the database. Keep the volume and `.env` during updates.

## Build images separately

Each image has a complete build context.

```bash
docker build -t statlab-frontend:ubuntu ./frontend
docker build -t statlab-backend:ubuntu ./backend
docker compose up -d --no-build --wait --wait-timeout 120
```

## Back up and restore PostgreSQL

Create a fresh PostgreSQL dump before updates or host migration.

```bash
docker compose exec -T database pg_dump -U statlab -d statlab -Fc > statlab-backup.dump
```

Restore into a fresh database using `pg_restore`. Keep backups outside the repository and protect them as application data.

## Refresh this package

After changing source files, regenerate the deployment copy and archive from the project root.

```powershell
.\.venv\Scripts\python.exe scripts\prepare_ubuntu.py
```

The generated package contains application source and SQL migrations. It excludes environment secrets, database volumes, and local backups.
