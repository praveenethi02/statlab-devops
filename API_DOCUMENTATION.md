# API documentation

Responses are JSON except HTML/static files and successful CSV/PDF downloads. Errors use `{"error":"human readable explanation"}`. Common statuses: 200 success, 201 created, 400 validation, 401 sign-in required/invalid credentials, 403 host/origin/CSRF failure, 404 missing or foreign-owned resource, 409 duplicate account/revision conflict, 413 body limit, 415 JSON required, 429 rate limit, 503 SQLite unavailable.

## Cookies and CSRF

First call `GET /api/me`, retain cookies, and send the returned `csrf_token` as `X-CSRF-Token` on every POST/PUT/DELETE, including signup and login. Cookies are HttpOnly and SameSite=Strict; HTTPS deployment sets Secure. Do not store passwords or authoritative datasets in localStorage. CSRF tokens expire after two hours; fetch `/api/me` again and retry the intended action. The frontend refreshes the token and asks the user to retry rather than automatically repeating a mutation.

| Method | Endpoint | Request / response |
|---|---|---|
| GET | `/api/health` | `{status:"ok"}` after a DB connectivity check; public |
| GET | `/api/me` | `{user:{username,email} or null,csrf_token}`; public |
| POST | `/api/signup` | `{username,email,password}` -> `{ok:true}`; public |
| POST | `/api/login` | `{identifier,password,remember?:boolean}` -> `{user,csrf_token}` + session cookie |
| POST | `/api/logout` | `{}` -> `{ok:true}`; deletes session |
| POST | `/api/profile/password` | `{current_password,new_password}`; invalidates every session |
| GET | `/api/datasets` | Optional `search`, `sort=updated|created|name`; `{datasets:[...]}` |
| POST | `/api/datasets` | `{name,description?,text}` OR `{name,description?,data}` -> `{dataset}` |
| GET | `/api/datasets/{id}` | `{dataset}` includes data, custom parameters and analysis count |
| PUT | `/api/datasets/{id}` | Full dataset payload plus required `revision`; returns updated dataset |
| DELETE | `/api/datasets/{id}` | Deletes owned dataset and all associated analyses/parameters |
| POST | `/api/datasets/{id}/duplicate` | `{}` -> copied dataset and dataset-scoped parameters |
| POST | `/api/import/csv` | Multipart `file`, `header=true|false`, `delimiter=,|;|tab character`; returns validated data, first 20 preview rows and row_count; does not save automatically |
| GET | `/api/statistics/catalog` | `{metrics:{key:{name,section,formula,description}}}` |
| POST | `/api/statistics/preview` | `{data or text,settings?}` -> transient `{calculation}` for unsaved data |
| POST | `/api/statistics/calculate` | `{dataset_id,settings?}` -> `{calculation,dataset_revision}` |
| POST | `/api/datasets/compare` | `{selections:[{dataset_id,settings?},...]}`; two to six entries -> `{comparisons}` |
| GET | `/api/analyses` | `{analyses:[summary...]}` with historical flag |
| POST | `/api/analyses` | `{name,dataset_id,dataset_revision,settings?}` -> server-computed `{analysis}` |
| GET | `/api/analyses/{id}` | `{analysis}` with calculation, immutable snapshot, latest custom parameters |
| DELETE | `/api/analyses/{id}` | Removes snapshot; keeps custom parameters at dataset scope |
| POST | `/api/analyses/{id}/duplicate` | `{}` -> copies saved snapshot and analysis-scoped parameters |
| GET | `/api/datasets/{id}/parameters` | `{parameters:[...]}` |
| POST | `/api/datasets/{id}/parameters` | Custom parameter payload -> `{parameter}` |
| PUT | `/api/parameters/{id}` | Full custom parameter payload -> `{parameter}` |
| DELETE | `/api/parameters/{id}` | `{ok:true}` |
| GET | `/api/datasets/{id}/export` | UTF-8 CSV download |
| GET | `/api/analyses/{id}/export?format=csv` | Statistical results + manual values CSV; default format |
| GET | `/api/analyses/{id}/export?format=pdf` | Paginated saved-analysis PDF with histogram and methodology |

All platform endpoints require authentication. Even calculate, compare, duplicate, parameter association, and export enforce ownership.

## Dataset format

```json
{
  "name": "Experiment 01",
  "description": "Measurements from trial one",
  "data": {
    "kind": "raw",
    "columns": ["Temperature", "Response"],
    "rows": [[10, 3], [20, 5], [30, null]]
  }
}
```

Kinds: `raw` for observations, `frequency` for `[value,frequency]`, `interval` for `[lower,upper,frequency]`. Names must be unique within the dataset; each row matches the column count. Null/empty cells remain missing. Text columns may be retained, but selected analysis columns must be numerical. Frequencies are nonnegative integers, total at most 10,000; intervals are ordered/nonoverlapping. Limits: 10,000 rows, 32 columns, 100,000 cells, 2 MB body, 500 characters per cell. Nonzero numerical magnitudes must be `1e-100` through `1e100`.

## Calculation settings

```json
{
  "dataset_id": 1,
  "settings": {
    "column": 0,
    "y_column": 1,
    "missing": "drop",
    "percentiles": [5, 25, 50, 75, 95],
    "weights": [1, 2, 1],
    "statistics": ["count", "mean", "sample_variance", "pearson", "spearman", "regression", "weighted_mean"]
  }
}
```

Indices are zero-based. `y_column` is optional and must differ from X. Weights are optional, one per source row including dropped rows; weighted and paired workflows require raw data. `statistics` defaults to all metrics. Missing policy defaults to `reject`; `drop` removes any row missing either selected variable. Percentile positions lie in [0,100]. Results include `results`, `issues`, `catalog`, `algorithm_version`, `conventions`, `settings`, `summary`, and `chart_data`. Undefined results are null with reason strings in `issues`. `summary.estimated=true` identifies class-midpoint estimates.

## Custom parameters

```json
{"name":"Experimental Error","value":2.5,"unit":"%","formula":"error / measurement","description":"Independent estimate","analysis_id":null}
```

Value is a finite number or nonempty text. Name max 120 characters; text value max 1000, unit 40, formula 500, description 2000. A supplied analysis ID must be owned and refer to the same dataset. Dataset-scoped parameters appear across its analyses; analysis-scoped parameters appear only in that saved analysis. Creation and modification timestamps are returned.
