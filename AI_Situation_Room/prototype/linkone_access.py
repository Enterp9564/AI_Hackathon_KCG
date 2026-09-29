"""Manual Link-One readiness checks; does not import data into HAEON."""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / '.secrets' / 'linkone'
ROOM = '4957a3fb-b012-4e9a-87e1-57b4301cf6b9'
HOST_FINGERPRINT = 'SHA256:RbdRpHgQVia1Ic9ZNRS0qLY9skVG24sCRkwYQse8QZ4'


def private_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or symbolic-link credential file')
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError('Credential file permissions must exclude group and others')
    return path


def local_check():
    import psycopg
    key = private_file(Path.home() / '.ssh' / 'haeon_linkone_ed25519')
    password = private_file(PRIVATE / 'db_password').read_text().strip()
    if not password:
        raise ValueError('DB password is empty')
    for name in ('known_hosts', 'ssh_config'):
        private_file(PRIVATE / name)
    derived = subprocess.run(['ssh-keygen', '-y', '-P', '', '-f', str(key)],
                             check=True, capture_output=True, text=True).stdout.split()[:2]
    if derived != key.with_suffix('.pub').read_text().split()[:2]:
        raise ValueError('Public/private key mismatch')
    fingerprint = subprocess.run(['ssh-keygen', '-lf', str(PRIVATE / 'known_hosts'),
                                  '-E', 'sha256'], check=True, capture_output=True,
                                 text=True).stdout.split()[1]
    if fingerprint != HOST_FINGERPRINT:
        raise ValueError('Server fingerprint mismatch')
    print(json.dumps({'local_ready': True, 'psycopg': psycopg.__version__,
                      'credentials_printed': False}))


def sync_check():
    # macOS system curl uses the system certificate trust store. Never use -k.
    url = 'https://114-110-181-118.sslip.io/api/sync?rooms=' + ROOM
    result = subprocess.run(['/usr/bin/curl', '--fail', '--silent', '--show-error',
                             '--proto', '=https', '--connect-timeout', '10',
                             '--max-time', '20', url],
                            check=True, capture_output=True, text=True, timeout=25)
    data = json.loads(result.stdout)
    if not isinstance(data, dict) or not isinstance(data.get('all'), str):
        raise ValueError('Unexpected sync response')
    rooms = data.get('rooms')
    if not isinstance(rooms, dict) or not isinstance(rooms.get(ROOM), str):
        raise ValueError('Missing test-room revision')
    print(json.dumps({'all': data['all'], 'rooms': {ROOM: rooms[ROOM]}}))


def tunnel():
    # Foreground only; Ctrl+C stops it. No remote shell or background daemon.
    os.execv('/usr/bin/ssh', ['ssh', '-F', str(PRIVATE / 'ssh_config'),
                            '-N', 'linkone-haeon'])


def db_check():
    import psycopg
    password = private_file(PRIVATE / 'db_password').read_text().strip()
    if not password:
        raise ValueError('DB password is empty')
    with psycopg.connect(host='127.0.0.1', port=15432, dbname='linkone',
                         user='linkone_ro', password=password, sslmode='disable',
                         connect_timeout=5, application_name='haeon-readiness',
                         options='-c default_transaction_read_only=on -c statement_timeout=10000') as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT current_database(), current_user, '
                        "current_setting('transaction_read_only')")
            db, user, readonly = cur.fetchone()
            if (db, user, readonly) != ('linkone', 'linkone_ro', 'on'):
                raise ValueError('Unexpected database identity or transaction mode')
            permissions = {}
            for table, column in [('account', 'password_hash'),
                                  ('device_credential', 'token_hash'),
                                  ('auth_session', 'token_hash'), ('band', 'secret')]:
                cur.execute('SELECT has_column_privilege(current_user, %s, %s, %s)',
                            ('public.' + table, column, 'SELECT'))
                allowed = cur.fetchone()[0]
                permissions[table + '.' + column] = allowed
                if allowed is not False:
                    raise ValueError('Excluded-column permissions differ from agreement')
            cur.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n "
                        "ON n.oid=c.relnamespace WHERE n.nspname='public' "
                        "AND c.relkind IN ('r','p') AND ("
                        "has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE') "
                        "OR has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE')) LIMIT 1000")
            if cur.fetchall():
                raise ValueError('Write privileges detected; stopped before data queries')
            queries = {
                'room': ('SELECT id, case_no, mode, status FROM public.room WHERE id=%s LIMIT 20'),
                'person': ('SELECT id, room_id, merged_into_id, not_boarded_at, removed_at, '
                           'roster_excluded_at FROM public.person WHERE room_id=%s ORDER BY id LIMIT 20'),
                'person_state': ('SELECT person_id, rescue, transit, management, severity, '
                                 'last_event_id, updated_at FROM public.person_state '
                                 'WHERE room_id=%s ORDER BY person_id LIMIT 20'),
                'person_event': ('SELECT id, type, server_at FROM public.person_event '
                                 'WHERE room_id=%s ORDER BY id DESC LIMIT 20'),
                'transfer': ('SELECT id, person_id, assigned_at, received_at, closed_at '
                             'FROM public.transfer WHERE room_id=%s ORDER BY id LIMIT 20'),
            }
            counts = {}
            for table, sql in queries.items():
                cur.execute(sql, (ROOM,))
                counts[table] = len(cur.fetchall())
            if counts['room'] != 1:
                raise ValueError('Agreed test room not found')
    print(json.dumps({'database': db, 'user': user, 'transaction_read_only': readonly,
                      'excluded_columns': permissions, 'sample_rows_max_20': counts,
                      'note': 'Sample sizes only; no person details printed or saved.'}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['local', 'sync', 'tunnel', 'db'])
    args = parser.parse_args()
    try:
        {'local': local_check, 'sync': sync_check, 'tunnel': tunnel, 'db': db_check}[args.action]()
    except Exception as exc:
        # Driver/network messages may contain sensitive connection details.
        print('Check failed: ' + type(exc).__name__ +
              '. See access README; no credentials or response bodies logged.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
