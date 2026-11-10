CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    salt BLOB NOT NULL,
    password_hash BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    expires REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires);
CREATE TABLE datasets (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
    description TEXT NOT NULL DEFAULT '',
    data_json TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX datasets_owner ON datasets(user_id, updated_at);
CREATE TABLE analyses (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    dataset_revision INTEGER NOT NULL,
    dataset_snapshot TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX analyses_owner ON analyses(user_id, created_at);
CREATE INDEX analyses_dataset ON analyses(dataset_id);
CREATE TABLE custom_parameters (
    id INTEGER PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    analysis_id INTEGER REFERENCES analyses(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    value_json TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    formula TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX parameters_dataset ON custom_parameters(dataset_id);
CREATE TABLE login_attempts (
    key TEXT NOT NULL,
    attempted_at REAL NOT NULL
);
CREATE INDEX attempts_lookup ON login_attempts(key, attempted_at);
