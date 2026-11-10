# StatLab - Statistical Data Analysis Workspace

A Python/SQLite application with a responsive HTML/CSS/JavaScript frontend. The original user table, PBKDF2 password hashes, session tokens, remember-me behavior, and `python server.py` launch command are retained. Account data is not replaced. Flask handles routing and validation; Waitress serves the application on Windows or Ubuntu.

## Run locally

Python 3.13+ and Node.js 22+ are recommended. Node is only needed to install the locally served chart library.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
.\.venv\Scripts\python.exe server.py
```

Ubuntu/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci
.venv/bin/python server.py
```

Open http://127.0.0.1:8000. The `/hrml` URL remains available. Existing accounts work with their existing passwords. Migrations run automatically and add tables without deleting users or sessions. A server CSRF signing key is generated beside the database if `APP_SECRET` is unset.

## What you can do

- Register, log in by username or email, remember sessions, sign out, and change your password.
- Create, search, sort, rename, duplicate, edit, and delete private datasets.
- Enter numerical text, edit spreadsheet cells, paste tab-separated Excel data, or preview UTF-8 CSV files.
- Analyze exact value frequencies or class intervals using clearly labeled midpoint estimates.
- Calculate descriptive, sample/population dispersion, position, distribution, frequency, weighted, correlation, and regression statistics.
- Choose a numerical column, missing-value policy, percentiles, weights, second variable, and selected statistics.
- Save reproducible analysis snapshots; editing observations marks earlier snapshots historical.
- Save numerical or textual custom parameters, units, formulas, and descriptions. Recalculation never overwrites them.
- Explore interactive histogram, bar, line, box, scatter, frequency, and cumulative charts; download chart PNGs.
- Compare two to six datasets, reopen history, export dataset/statistics CSV, download PDF reports, and print results.
- Use light/dark themes and responsive mobile navigation. Only the theme preference is stored in localStorage.

## Reference workflow

Create **Experiment 01** with `10, 20, 30, 40, 50` (the editor also has a sample button). Save and analyze. Mean and median are 30; population variance is 200; population standard deviation is 14.1421; sample variance is 250; sample standard deviation is 15.8114. Save the analysis, add **Experimental Error = 2.5 %**, sign out and back in, and reopen the saved report. Edit the dataset to generate new statistics while keeping the earlier saved result historical.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m unittest discover -v
npm run check
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scripts\browser_test.py
```

On Windows, if browser installation is unavailable and Edge is installed, set `$env:BROWSER_CHANNEL='msedge'` before the browser command. On Ubuntu use `.venv/bin/python`, install Chromium with `python -m playwright install --with-deps chromium`, and create `.runtime` first. Tests use temporary databases; no test creates accounts in your real database.

## Docker and LAN

For a self-contained Ubuntu package with separate frontend/backend folders, use [ubuntu-deploy/README.md](ubuntu-deploy/README.md). Refresh the package with `python scripts/prepare_ubuntu.py`; the transfer ZIP is written to `output/statlab-ubuntu.zip`. The original project remains the development source, and its existing Compose setup continues to work.

```bash
cp .env.example .env
# Windows PowerShell: Copy-Item .env.example .env
# First-time setup only: do not overwrite an existing .env.
# Generate APP_SECRET with python -c "import secrets; print(secrets.token_hex(32))"
# Paste it into .env and add your server IP to ALLOWED_HOSTS for LAN access.
docker compose up --build -d
docker compose ps
docker compose logs -f frontend backend
```

Open **http://localhost:8080** on this machine, or `http://UBUNTU_SERVER_IP:8080` from the LAN. The `frontend` service serves HTML/CSS/JavaScript with Nginx and forwards `/api/` to the `backend` Python service on internal port 8000. Login, datasets, and calculations require both services. SQLite lives in the persistent `statlab-data` volume.

After source or Dockerfile changes, run `docker compose up --build -d` again. `docker compose restart` alone does not apply a new image. After replacing only the backend, restart the frontend with `docker compose restart frontend` so Nginx resolves the backend's current container address. Local Docker Desktop images, running containers, static assets, and API health were verified on 2026-10-13; access from a second LAN computer and Ubuntu deployment remain unverified. See [DEPLOYMENT.md](DEPLOYMENT.md) for migration, backups, and deployment instructions.

## Conventions and limits

Quartiles/percentiles use type-7 linear interpolation. Skewness and excess kurtosis use sample bias corrections. Z-scores use population spread. CV uses sample spread divided by the absolute mean. Missing selected values are rejected unless explicitly dropped; paired analysis drops whole pairs. Undefined results are null with explanations.

Limits: 2 MB request/upload size; 10,000 rows or expanded frequencies; 32 columns; 100,000 cells. Nonzero numerical magnitudes must lie between `1e-100` and `1e100` to keep squared statistics within floating-point range. Class-interval results are estimates. No email verification, password reset service, shared workspaces, or remote deployment target is configured. PDF reports include a generated histogram; other chart types export separately as PNG. Long observation arrays and frequency tables are summarized in PDF and remain complete in CSV.

See [ARCHITECTURE.md](ARCHITECTURE.md), [API_DOCUMENTATION.md](API_DOCUMENTATION.md), [DEVELOPMENT_PROGRESS.md](DEVELOPMENT_PROGRESS.md), and [TEST_REPORT.md](TEST_REPORT.md).
