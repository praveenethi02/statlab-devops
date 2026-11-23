"""PostgreSQL connections and serialized, transactional schema migrations."""
from contextlib import closing
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS = Path(__file__).parent / 'database' / 'postgresql'
PostgresError = psycopg.Error
INTEGRITY_ERRORS = (psycopg.IntegrityError,)


class PostgresConnection(psycopg.Connection):
    def execute(self, query, params=None, **kwargs):
        # Application queries use qmark placeholders. All query text is internal.
        if params is not None:
            query = query.replace('?', '%s')
        return super().execute(query, params, **kwargs)


def connect(url):
    if not url.startswith(('postgresql://', 'postgres://')):
        raise ValueError('DATABASE_URL must be a PostgreSQL connection URL.')
    return PostgresConnection.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=15)


def transaction(connection):
    return connection.transaction()


def initialize(url):
    with closing(connect(url)) as db, db.transaction():
        # Serialize schema upgrades across API replicas starting together.
        db.execute('SELECT pg_advisory_xact_lock(73401720)')
        db.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        for migration in sorted(MIGRATIONS.glob('*.sql')):
            exists = db.execute(
                'SELECT 1 FROM schema_migrations WHERE version=?',
                (migration.name,),
            ).fetchone()
            if not exists:
                db.execute(migration.read_text(encoding='utf-8'))
                db.execute(
                    'INSERT INTO schema_migrations(version) VALUES (?)',
                    (migration.name,),
                )
