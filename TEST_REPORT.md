# Test report - 2026-10-13

## Separate Ubuntu deployment verification - 2026-10-19

- All 51 application tests passed in 20.279 seconds, including the new API-only mode check for frontend-free backend deployment. Ruff passed for changed code and the deployment package.
- Both self-contained Docker contexts in `ubuntu-deploy/frontend` and `ubuntu-deploy/backend` built successfully. An isolated `statlab-ubuntu-check` project ran on localhost port 8081 with its own named database volume; both container health checks passed.
- Static assets and `/api/health` returned HTTP 200. Registration, login, dataset creation, mean 30, and population variance 200 passed through Nginx. Nginx configuration validation passed; backend image contained neither `hrml` nor `static`.
- Test accounts and datasets survived full container recreation. The original project remained running on port 8080 and returned HTTP 200.
- Environment generation refused to overwrite an existing signing key. ZIP inspection confirmed the independent source folders and exclusion of `.env`, databases, secrets, local dependencies and exported Docker images.
- Actual Ubuntu server deployment, LAN access and hosted GitHub Actions execution remain unverified. CI now prepares and builds the separate Ubuntu package.

## Executed results

| Check | Actual result |
|---|---|
| Original baseline `python -m unittest -v test_server.py` | 2 tests passed before implementation; required loopback permission |
| Current `python -m unittest discover -v` | All 50 tests passed together in 20.746 seconds (31 statistics, 19 API/persistence/security/report tests) |
| `npm run check` | JavaScript syntax checks passed |
| `python -m ruff check .` | Passed after implementation and deployment changes |
| `python scripts/browser_test.py` with installed Edge | 10 workflow groups passed, no browser errors |
| PDF text verification | Passed: saved dataset, statistics, historical flag, manual parameter, methodology |
| PDF visual QA | All five reference report pages rendered and inspected; clean layout, headings and complete custom-parameter rows |
| Production entry point `python server.py` | Waitress started successfully; actual app `/` and `/api/health` returned HTTP 200; temporary preview stopped after verification |
| Actual database preservation | Online backup completed; original user/session rows unchanged byte-for-byte; integrity check `ok`, no foreign key violations |
| Docker build/container health | Frontend and backend rebuilt on Docker Desktop; both running on latest images; backend healthy; page, API health, API session endpoint, JavaScript and Plotly assets return HTTP 200 |
| Docker update/data preservation | Online backup before container replacement; all users, sessions, datasets and analyses rows match the backup; SQLite integrity `ok` and no foreign key violations; packaged backup utility verified |
| Frontend Nginx configuration | `nginx -t` passed inside the running frontend container |
| Docker backup/restore utility | Backup passed in running backend; restore from local backup passed into disposable container's `/tmp`, with integrity `ok` |
| Exported Docker images | Both `.tar` archives refreshed from current images; archive manifests confirm frontend/backend image tags |
| Another computer on LAN | Not executed: no Ubuntu/LAN deployment target supplied |
| GitHub Actions hosted run | Workflow written; not triggered from this environment |

## Coverage

Numerical tests use reference datasets and floating-point tolerances for mean, median, multimode/no-mode, variance/std for both denominators, type-7 quartiles/percentiles, IQR, bias-corrected skewness/kurtosis, z-scores, positive-only means, weights, Pearson/Spearman with average-rank ties, regression and R², grouped exact frequencies, class-midpoint estimates, outlier detection, invalid/empty/single/identical/negative/decimal/missing values, limits and selected metrics.

API tests cover original account behavior, case-insensitive identifiers, remember-me cookies, session expiry, password changes invalidating all sessions, rate limiting/expiry, CSRF token and Origin checks, host/header protection, malformed input, CSV encoding/header/ragged rows/extension/size/row limits, safe CSV spreadsheet exports, SQL injection attempts, dataset CRUD and duplication, analysis duplication/deletion, custom-parameter lifecycle/associations, snapshot/revision conflicts, migration preservation, online backup, cross-user denial for every private operation including export/compare, and persistence after app recreation with a fresh client.

Additional regressions verify password whitespace compatibility with the original hashing behavior and PDF generation for 1,000 distinct values with maximum-length custom values/formulas/descriptions. The real account database was backed up and migrated, with its original user/session rows preserved byte-for-byte and both integrity/foreign-key checks passing.

After the combined run, targeted CSV/PDF tests passed again following two export refinements: signed numeric strings round-trip without formula-protection apostrophes, and PDF formulas preserve `xbar` for the sample mean. Updated PDF pages were rendered for visual QA. No subsequent calculation or frontend behavior changed.

The reference end-to-end test registers/logs in, creates Experiment 01, verifies mean 30/population variance 200/sample variance 250, saves an analysis and Experimental Error 2.5%, logs out, recreates the server application, signs in on a fresh client, recovers work, edits observations, verifies a changed mean and historical original result, and exports a PDF.

Browser checks run a real temporary Waitress HTTP server and Playwright against installed Microsoft Edge. They verify form interactions and server persistence, reference statistics (including standard deviations), all seven chart choices, save/reopen, manual values, exports, paired CSV workflow, comparison, dark mode and mobile overflow checks. Browser accounts/data are confined to a temporary database, removed after tests. Screenshots, sample report downloads and `browser-report.json` are stored in ignored `test-results/`.

## Environment and limitations

Windows development host; Python 3.14.4; Node 24.18.1. Docker targets Python 3.13 and Node 22. Backend tests use Flask's in-process client, so they do not depend on network permissions. Original baseline and browser HTTP tests needed network permission. Playwright's Chromium download failed due to external connection reset/timeouts; installed Edge succeeded as an alternate supported test browser. Docker Desktop builds and localhost routing were verified on 2026-10-13. Ubuntu deployment and real LAN routing remain verification tasks; CI now builds and smoke-tests both Compose services, but a hosted run has not been triggered here.

Tests never delete or replace `accounts.sqlite3`. PDF reports use latest editable custom parameter values and explicitly label that policy; calculated snapshots remain immutable. Large arrays and frequency distributions are summarized in PDF with full CSV data available. No performance/load testing, email verification/recovery integration, public TLS deployment, or automated remote rollout was performed.
