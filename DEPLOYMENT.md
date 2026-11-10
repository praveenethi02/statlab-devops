# Docker Desktop, Ubuntu, and LAN deployment

For the separate frontend/backend Docker folders requested for Ubuntu hosting, use the self-contained [ubuntu-deploy](ubuntu-deploy/README.md) package. Each service builds entirely from its own folder. Run `python scripts/prepare_ubuntu.py` from this project's root to refresh its source copies and `output/statlab-ubuntu.zip`. The instructions below describe the original project's Compose setup.

Docker Desktop (Linux containers) on Windows or Docker Engine with the Compose plugin on Ubuntu is required. The current deployment builds two images: `statlab-frontend:latest` (Nginx and static assets) and `statlab-backend:latest` (Python API and SQLite). Local images, container health, static assets, and API routing were verified on Windows Docker Desktop on 2026-10-13. Ubuntu and access from another LAN computer remain unverified.

## Run or update on this Windows machine

From the project folder, with Docker Desktop running:

```powershell
# For first-time setup only, if .env does not exist:
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
# Paste the generated value into APP_SECRET in .env.
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 frontend backend
Invoke-RestMethod http://localhost:8080/api/health
```

Open **http://localhost:8080**. Keep the existing `.env` when updating. After changing source, Dockerfiles, or Nginx configuration, run `docker compose up --build -d` again. If both images are already built or loaded, use `docker compose up -d`. A plain `docker compose restart` does not replace a container with a newly built image. When replacing only the backend, run `docker compose restart frontend` afterward so Nginx resolves the backend's current container address.

## Export and load built images

The image archives in this project can be recreated from the latest local builds:

```powershell
docker image save --output statlab-frontend.tar statlab-frontend:latest
docker image save --output statlab-backend.tar statlab-backend:latest
```

On another Docker host with the same architecture (`linux/amd64` for these local images), transfer the archives and `compose.yaml`, then load and start them:

```bash
docker image load --input statlab-frontend.tar
docker image load --input statlab-backend.tar
# Create .env with APP_SECRET and the destination's ALLOWED_HOSTS.
docker compose up -d --no-build
```

Images do not contain the SQLite database or `.env`. To preserve accounts and datasets on a new host, back up and restore the database using the instructions below. Use the same APP_SECRET if preserving signing continuity.

## Start on a trusted LAN

```bash
cp .env.example .env
hostname -I
```

Copy `.env.example` only on first-time setup. Edit `.env`: put your actual server IP in `ALLOWED_HOSTS`, retaining `localhost,127.0.0.1` for health checks. Example: `ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.100`. Keep `COOKIE_SECURE=false` for HTTP on a trusted LAN. Generate `APP_SECRET` with `python3 -c "import secrets; print(secrets.token_hex(32))"` and paste it into `.env`; Compose requires a nonempty value. Set `BIND_ADDRESS=0.0.0.0` for LAN access. Keep `.env` out of source control.

```bash
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 frontend backend
curl --fail http://127.0.0.1:8080/api/health
```

Visit **http://UBUNTU_SERVER_IP:8080** from another computer on the same Ethernet/LAN network. Compose publishes Nginx port 80 as host port 8080. Nginx forwards `/api/` to `backend:8000`; the backend's port is internal and is not published on the host. If Ubuntu's firewall is enabled, restrict access to the actual LAN subnet (replace the example):

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8080 proto tcp
```

Docker-published ports can bypass normal UFW rules; enforce subnet restrictions in the Docker firewall chain or an upstream firewall as needed. Do not forward port 8080 on your router for public access.

The named `statlab-data` volume stores SQLite and WAL files. Compose supplies the signing key through `APP_SECRET` in `.env`; preserve it across updates. `docker compose restart` and `docker compose down` retain the volume. `docker compose down -v` deletes persistent data and must not be used unless deliberately destroying the workspace. The backend runs as UID/GID 10001, with a read-only application filesystem and temporary `/tmp`. `init: true` forwards termination signals; Waitress waits for active workers before shutdown. Logs are sent to stdout/stderr.

## Preserve existing accounts when first moving to Docker

The image intentionally excludes account databases and secrets. Make an online backup of the existing DB first; do not copy a live SQLite file without its WAL state.

On the current machine:

```powershell
New-Item -ItemType Directory -Force migration | Out-Null
.\.venv\Scripts\python.exe scripts\maintenance.py backup --source accounts.sqlite3 --target migration\accounts.sqlite3
```

Transfer the backup securely to `migration/accounts.sqlite3` on Ubuntu. For a **new, empty Docker volume**, restore before starting the service:

```bash
docker compose build
docker compose run --rm --no-deps --user root --cap-add CHOWN --cap-add DAC_OVERRIDE \
  -v "$(pwd)/migration:/migration" backend \
  python scripts/maintenance.py restore \
  --source /migration/accounts.sqlite3 \
  --target /data/accounts.sqlite3 --owner 10001
docker compose up -d
```

The restore command refuses to overwrite an existing target. The one-off restore grants the capabilities needed to write the backend-owned directory and set the restored file's owner; the normal service still drops all capabilities. Mount the backup directory writable so SQLite can create temporary journal files when reading a WAL-mode backup. Keep any preexisting volume safe; use a separate empty volume for a restore or migration. Original users, salted hashes, and unexpired sessions remain in the restored database. New signing keys require fetching a fresh CSRF token. Cookie session continuity also depends on hostname/browser cookie scope; users can always sign in again on the new hostname.

## Backups

Use the SQLite online backup API, which includes committed WAL transactions:

```bash
mkdir -p backups
docker compose exec backend python scripts/maintenance.py backup \
  --source /data/accounts.sqlite3 --target /data/backup-2026-10-13.sqlite3
docker compose cp backend:/data/backup-2026-10-13.sqlite3 ./backups/
```

Choose a new filename for each backup. Store backups encrypted and outside the host; verify `PRAGMA integrity_check` and rehearse restoring into an empty volume. Preserve `.env`/APP_SECRET or the generated `accounts.secret` securely if you need CSRF signing continuity. Keep backups and database files outside public static directories. In production, schedule backup and retention outside the app using your normal server operations tools.

## Public deployment over HTTPS

1. Put a maintained Nginx/Caddy reverse proxy and a TLS certificate in front of the frontend on host port 8080. Bind the frontend to `127.0.0.1` with `BIND_ADDRESS=127.0.0.1` in `.env` and recreate it with `docker compose up -d`.
2. Set `ALLOWED_HOSTS=localhost,127.0.0.1,stats.example.com`, `COOKIE_SECURE=true`, and a strong persistent `APP_SECRET`.
3. The included frontend configuration supports HTTP LAN use. Before adding an outer HTTPS proxy, configure frontend Nginx to accept traffic only from that trusted proxy and preserve its verified `X-Forwarded-Proto: https` header when forwarding `/api/`. The current `proxy_set_header X-Forwarded-Proto $scheme` would replace it with `http`, causing HTTPS Origin checks to fail.
4. Set `TRUSTED_PROXY` to the exact frontend-container address Waitress sees, using a stable address for that deployment. Avoid a wildcard. Waitress clears forwarded scheme/client IP headers from untrusted addresses. Have both proxy hops preserve the original `Host` (including a nondefault port) and supply verified client IP information. Rebuild the frontend after modifying `nginx.conf`. This HTTPS topology has not been configured or verified locally.

Example Nginx location inside an HTTPS server block:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $remote_addr;
    client_max_body_size 2m;
}
```

Terminate plain HTTP at the proxy with a redirect to HTTPS. Configure patching, backup monitoring, disk capacity alerts, trusted administrators, and access log retention for your environment. Account email verification and password recovery are not implemented; add an authenticated email provider/recovery workflow before operating a public service that needs those features. The built-in attempt limits are application safeguards; a public deployment should additionally use proxy-level traffic controls.

## CI/CD

`.github/workflows/ci.yml` checks Python quality, numerical/persistence/security tests, JavaScript syntax, a real browser workflow, Docker build, and container health. It uploads browser evidence on failure/success. There is no remote deployment job or stored deployment credential. To add one, select a server and a protected GitHub environment, store SSH/deployment credentials in GitHub Secrets, and require explicit environment approval before a rollout. Never echo credentials into build logs.

## Local environment variables

Direct Python execution defaults `HOST` to 127.0.0.1, `PORT` to 8000, `DATABASE_PATH` to the existing repository database, `ALLOWED_HOSTS` to localhost/127.0.0.1, and `COOKIE_SECURE` to false. Direct Python execution can generate a sidecar key if `APP_SECRET` is unset; Compose requires an explicit `APP_SECRET` and reads `.env` automatically. Compose fixes the backend's internal port to 8000 and exposes the frontend on host port 8080; `BIND_ADDRESS` controls the frontend's host interface. Direct Python execution requires exporting environment variables; for direct LAN use set HOST=0.0.0.0 and include the server IP in ALLOWED_HOSTS.
