"""Create isolated PostgreSQL schemas for test runs."""
import os
import secrets
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg import sql


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
        parts = urlsplit(self.base_url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        query.append(('options', f'-c search_path={schema}'))
        query_string = urlencode(query, quote_via=quote)
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, query_string, parts.fragment)
        )

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
