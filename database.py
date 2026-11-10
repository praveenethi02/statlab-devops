"""Additive, transactional schema migration; original users and sessions stay intact."""
import sqlite3
from contextlib import closing
from pathlib import Path

MIGRATIONS = Path(__file__).parent / 'migrations'


def connect(path):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('PRAGMA busy_timeout = 15000')
    return db


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as db:
        db.execute('PRAGMA journal_mode = WAL')
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        db.commit()
        for file in sorted(MIGRATIONS.glob('*.sql')):
            if db.execute('SELECT 1 FROM schema_migrations WHERE version=?', (file.name,)).fetchone():
                continue
            try:
                db.executescript('BEGIN IMMEDIATE;\n' + file.read_text(encoding='utf-8'))
                db.execute('INSERT INTO schema_migrations(version) VALUES (?)', (file.name,))
                db.commit()
            except Exception:
                db.rollback()
                raise


def backup(source, target):
    """Online SQLite backup includes committed WAL state; never copy a live DB directly."""
    with closing(connect(source)) as db, closing(sqlite3.connect(target)) as output:
        db.backup(output)
