# StatLab: separate frontend and backend for Ubuntu

This folder is a self-contained deployment copy. Transfer this whole folder to Ubuntu, or unzip `output/statlab-ubuntu.zip` from the original project. The server does not need files from the original project directory.

```text
ubuntu-deploy/
  frontend/
    Dockerfile          Nginx image with a Node build stage for chart assets
    index.html          Website entry point
    static/             Website JavaScript, CSS, and icon
    nginx.conf          Serves the website and forwards /api/ to backend:8000
    package*.json       Pinned chart dependency
    scripts/vendor.mjs  Copies chart assets during the image build
  backend/
    Dockerfile          Python API image; no frontend files
    server.py           API launch command
    app_backend.py      Account, dataset, and analysis API
    database.py         SQLite connection and migrations
    statistics_engine.py
    reports.py
    requirements.txt
    migrations/
    scripts/maintenance.py
  compose.yaml          Builds and runs both services with persistent storage
  .env.example          Configuration reference; contains no signing secret
  setup_env.py          Generates a fresh .env without overwriting an existing one
```

## Start on Ubuntu

Prerequisites: Ubuntu with Docker Engine and the Docker Compose plugin installed, Python 3, and internet access for the first image build. Run the following commands from this folder:

```bash
python3 setup_env.py --host YOUR_UBUNTU_SERVER_IP
docker compose up -d --build --wait --wait-timeout 120
docker compose ps
curl --fail http://localhost:8080/api/health
```

Replace `YOUR_UBUNTU_SERVER_IP` with the actual server address. `setup_env.py` creates a random APP_SECRET and adds the address to ALLOWED_HOSTS. It refuses to overwrite an existing `.env`; edit that file directly when configuration changes. Repeat `--host` for more addresses, for example `--host 192.168.1.20 --host stats.internal`. Add `--port 80` if the server should publish HTTP on port 80 instead of 8080.

Open **http://YOUR_UBUNTU_SERVER_IP:8080**. Allow the chosen HTTP port through the server or network firewall as appropriate. This package serves HTTP; public HTTPS needs a separate TLS/proxy configuration. It has not been deployed to your Ubuntu server yet.

The frontend receives browser requests and forwards `/api/` over the private Compose network. The backend's port 8000 is not published on the server. Keep both services on this network; the supplied Nginx configuration expects the backend service name `backend`. The backend stores accounts and datasets in the `statlab-data` named volume (`statlab_statlab-data` by default). A fresh server starts with an empty database unless you migrate existing data.

## Build each image independently

Each folder has its own complete Docker build context:

```bash
docker build -t statlab-frontend:ubuntu ./frontend
docker build -t statlab-backend:ubuntu ./backend
docker compose up -d --no-build --wait --wait-timeout 120
```

An Ubuntu server with a different CPU architecture builds images for that server automatically. Locally saved Docker image archives need a matching architecture.

## Move your existing Docker database to Ubuntu

If you want your current accounts and datasets, back up the running Docker database on Windows. In the **original project folder**, choose a new backup filename and run:

```powershell
New-Item -ItemType Directory -Force output\migration | Out-Null
docker compose exec backend python scripts/maintenance.py backup --target /data/ubuntu-transfer.sqlite3
docker compose cp backend:/data/ubuntu-transfer.sqlite3 output/migration/accounts.sqlite3
```

Transfer that backup separately to `ubuntu-deploy/migration/accounts.sqlite3` on Ubuntu. The ZIP intentionally contains neither database data nor your existing `.env`. If you need the current signing key to remain the same, transfer it securely into the Ubuntu `.env` as APP_SECRET; do not put it in the ZIP.

On Ubuntu, **before the first startup**, create `.env`, build the images, and restore into the new empty volume:

```bash
python3 setup_env.py --host YOUR_UBUNTU_SERVER_IP
docker compose build
docker compose run --rm --no-deps --user root --cap-add CHOWN --cap-add DAC_OVERRIDE \
  -v "$PWD/migration:/migration" backend \
  python scripts/maintenance.py restore --source /migration/accounts.sqlite3 \
  --target /data/accounts.sqlite3 --owner 10001
docker compose up -d --wait --wait-timeout 120
```

Skip the setup command if `.env` already exists. Restore refuses to overwrite an existing database. If you already started the new server, preserve its volume and select a separate empty volume before restoring. The temporary restore container gets the capabilities needed to write the data directory and set file ownership; the normal backend drops all capabilities. The backup directory is writable for SQLite journal sidecars.

## Backup, update, and stop

Choose a new backup filename each time:

```bash
mkdir -p backups
docker compose exec backend python scripts/maintenance.py backup --target /data/backup-before-update.sqlite3
docker compose cp backend:/data/backup-before-update.sqlite3 ./backups/
docker compose up -d --build --wait --wait-timeout 120
docker compose restart frontend
docker compose logs --tail=100 frontend backend
```

Restarting the frontend after a backend replacement makes Nginx resolve its current address. `docker compose down` stops the stack and keeps its data volume; `docker compose down -v` deletes that volume and its database. Keep `.env` and database backups across updates.

## Refresh this deployment copy after editing the original project

The original project remains the development source. From its root on Windows:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_ubuntu.py
```

On systems using a standard Python installation, use `python3 scripts/prepare_ubuntu.py`. The script refreshes the frontend/backend source copies and writes `output/statlab-ubuntu.zip`. It packages an explicit list of deployment files and excludes account databases, secrets, `.env`, local dependencies, and exported images. Refresh the copy before transferring source updates to Ubuntu; preserve the server's own `.env` and Docker volume.

## Local verification (2026-10-19)

Both folders built independently as Linux Docker images and ran together in an isolated Docker Desktop Compose project. Both health checks passed. Website assets, API health, registration, login, dataset saving, and reference statistics were verified through Nginx. Accounts and datasets survived container recreation. The backend image contains no frontend files. The application suite passed all 51 tests. This verifies the Linux containers locally; deployment and network access on your Ubuntu server still need to be checked there.
