# Development progress

## Separate Docker folders for Ubuntu - 2026-10-19

- Added the self-contained `ubuntu-deploy` package with independent `frontend` and `backend` build contexts, Compose, configuration generation, migration instructions, and a transfer ZIP at `output/statlab-ubuntu.zip`.
- Added API-only mode to the shared backend so the separated Python image needs no frontend assets. Direct development serving remains enabled by default.
- Added `scripts/prepare_ubuntu.py` to refresh source copies and archive only explicitly selected deployment files. Databases, secrets, `.env`, local dependencies, and image archives are excluded.
- All 51 application tests and changed-code Ruff checks passed. Both Linux images built, both services became healthy, and registration/login/dataset/calculation checks passed through Nginx in a separate test project on port 8081.
- Accounts and datasets survived test-container recreation. Existing port-8080 deployment and its volume were retained. Ubuntu hosting itself remains unverified until the package is transferred to the server.

## Audit - 2026-10-13

- Completed: reviewed all application source, original tests, SQLite schema, and repository status.
- Completed: verified one existing user and one session; existing account database will be preserved.
- Completed: identified PBKDF2-SHA256 (600,000 rounds), hashed session tokens, remember-me expiry, and private-file allowlisting.
- Completed baseline: original two HTTP account tests passed with network permission after the sandbox blocked loopback connections.
- Existing limitations: localhost-only development server, no CSRF tokens/rate limiting, no datasets/analysis schema, no deployment configuration.
- At the initial audit, Docker verification was blocked because the executable was not installed. Docker Desktop is now installed; local builds and container checks passed later on 2026-10-13.

## Implementation plan

1. Preserve original users/sessions and password algorithm; introduce additive SQLite migrations and a Flask/Waitress web layer with CSRF and account protection.
2. Implement structured datasets, revisions, exact/grouped statistics, saved analysis snapshots, custom parameters, imports and exports.
3. Build a responsive vanilla HTML/CSS/JavaScript workspace with Plotly charts, editors, history, comparison, and settings.
4. Add numerical, persistence, security, and browser tests; verify PDF layout.
5. Add Docker/Compose, CI, and architecture/API/deployment documentation; record actual verification results.

## Feature status

| Feature | Status | Evidence |
|---|---|---|
| Existing accounts | Completed audit | Original schema inspected; account database retained |
| Dataset management | Completed | CRUD, search/sort, duplication, revisions and conflict checks; API/browser tests |
| Statistical engine | Completed | 31 numerical tests; reference experiment and edge cases pass |
| Saved analyses and custom parameters | Completed | Snapshots, historical flags, manual values and associations; restart/ownership tests |
| Frontend workspace | Completed | All nine required page workflows, responsive navigation, light/dark themes |
| CSV/grouped data/charts/comparison/exports | Completed | Validated imports, exact/grouped estimates, seven chart choices, comparisons, CSV/PDF/PNG exports |
| Security and tests | Completed | All 50 unit/integration tests passed together; ten browser workflow groups passed without JS errors; Ruff and JS syntax passed |
| Docker and CI | Local Docker verified; hosted CI run unverified | Frontend/backend images rebuilt and running; persistent volume retained; API health and static assets return HTTP 200; CI checks current two-service Compose deployment |
| Final validation | Completed locally; external deployment checks remain | PDF pagination and mobile/desktop screenshots verified previously; production and Docker HTTP checks passed; second-computer LAN and Ubuntu checks pending |

## Validation notes

- Existing account hashing and session formats retained; migration preservation covered by an original-schema fixture.
- Chromium download failed with timeout/connection resets. Browser tests succeeded using installed Microsoft Edge through Playwright; CI uses downloaded Chromium on Ubuntu.
- Full browser flow verified reference numbers, analysis saving, custom parameter creation/editing, logout/login/reload, changed observations, historical results, CSV/PDF downloads, CSV paired input, scatter/correlation, comparison, mobile layout and dark mode.
- Desktop/mobile and dark-mode screenshots reviewed; PDF rendered with bundled Poppler. Section headings, frequency tables, page numbering and long-value truncation verified; a large-report pagination regression also passes.
- Actual database migrated after online backup to `.runtime/accounts-before-platform.sqlite3`; original users and sessions compared byte-for-byte. SQLite integrity and foreign key checks passed.
- Final combined suite: 50 tests passed in 20.746 seconds. Ruff, JavaScript syntax checks, and ten browser workflow groups passed. Additional targeted CSV/PDF regressions passed after export formatting fixes.
- Production `python server.py` started with Waitress and the actual migrated database; `/` and `/api/health` returned HTTP 200. Local preview was queued in Codex, and the temporary server was stopped after verification. Use the README command to run it again.
- Local Docker Desktop builds and container health passed on 2026-10-13. Ubuntu deployment, second-computer LAN access, and hosted GitHub Actions execution remain unverified. Deployment configuration and instructions are supplied.
- No remote deployment or cloud service used; authoritative data remains in the existing SQLite architecture.

## Docker update - 2026-10-13

- Corrected the backend image to include the maintenance utility and made the frontend's port 8080 binding respect `BIND_ADDRESS`. Excluded exported image archives from Docker build context.
- Created an online database backup in the Docker volume and copied it to `.runtime/docker-before-update-20261013T101050Z.sqlite3` before rebuilding and recreating both services.
- Confirmed both containers use their latest images; backend health, page, API session endpoint, JavaScript and Plotly requests returned HTTP 200. Nginx configuration validation passed.
- Compared all users, sessions, datasets and analyses rows against the pre-update backup; all were preserved. SQLite integrity passed with no foreign key violations. Backup and temporary restore checks passed.
- Refreshed both exported `.tar` images and updated README, deployment instructions, environment template and CI to match the two-service configuration. Hosted CI, Ubuntu and second-computer LAN checks remain unverified.
