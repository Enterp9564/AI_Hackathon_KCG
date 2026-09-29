"""Credential and read-only guards, without network or real credentials."""
import contextlib
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from prototype import linkone_access as access


class FakeDB:
    def __init__(self, exposed=False, writable=False):
        self.exposed = exposed
        self.writable = writable
        self.statements = []
        self.sql = ''

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self.sql = sql
        self.statements.append((sql, params))

    def fetchone(self):
        if 'current_database()' in self.sql:
            return ('linkone', 'linkone_ro', 'on')
        return (self.exposed,)

    def fetchall(self):
        if 'pg_class' in self.sql:
            return [('room',)] if self.writable else []
        return [('synthetic-row',)]


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.password = self.folder / 'db_password'
        self.password.write_text('test-only-not-a-real-password')
        self.password.chmod(0o600)

    def run_check(self, db):
        calls = []

        def connect(**kwargs):
            calls.append(kwargs)
            return db

        with patch.object(access, 'PRIVATE', self.folder), patch.dict(
                'sys.modules', {'psycopg': types.SimpleNamespace(connect=connect)}):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                access.db_check()
        return calls, output.getvalue()

    def test_readonly_options_and_no_row_or_password_output(self):
        db = FakeDB()
        calls, output = self.run_check(db)
        self.assertIn('default_transaction_read_only=on', calls[0]['options'])
        self.assertEqual(calls[0]['host'], '127.0.0.1')
        self.assertNotIn('test-only-not-a-real-password', output)
        self.assertNotIn('synthetic-row', output)
        self.assertTrue(all(sql.startswith('SELECT ') for sql, _ in db.statements))
        data_queries = [(sql, args) for sql, args in db.statements if 'FROM public.' in sql]
        self.assertEqual(len(data_queries), 5)
        self.assertTrue(all('LIMIT 20' in sql and args == (access.ROOM,)
                            for sql, args in data_queries))

    def test_excluded_column_access_stops_before_data(self):
        db = FakeDB(exposed=True)
        with self.assertRaises(ValueError):
            self.run_check(db)
        self.assertFalse(any('FROM public.' in sql for sql, _ in db.statements))

    def test_write_permission_stops_before_data(self):
        db = FakeDB(writable=True)
        with self.assertRaises(ValueError):
            self.run_check(db)
        self.assertFalse(any('FROM public.' in sql for sql, _ in db.statements))

    def test_world_readable_password_is_rejected(self):
        self.password.chmod(0o644)
        with self.assertRaises(ValueError):
            access.private_file(self.password)

    def test_symlink_password_is_rejected(self):
        target = self.folder / 'alias'
        target.symlink_to(self.password)
        with self.assertRaises(ValueError):
            access.private_file(target)


if __name__ == '__main__':
    unittest.main()
