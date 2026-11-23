"""Create isolated PostgreSQL schemas for test runs."""
import os
import secrets

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo


class PostgresTestSchemas:
    def __init__(self):
        self.base_url = os.environ.get('DATABASE_URL')
        if not self.base_url:
            raise RuntimeError('Set DATABASE_URL to a PostgreSQL test database.')
        self.admin = psycopg.connect(self.base_url, autocommit=True)
        self.schemas = []

    def create(self):
        schema = 'statlab_test_' + secrets.token_hex(8)
        self.admin.execute(
            sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema))
        )
        self.schemas.append(schema)
        return make_conninfo(self.base_url, options=f'-c search_path={schema}')

    def close(self):
        for schema in reversed(self.schemas):
            self.admin.execute(
                sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema))
            )
        self.admin.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
