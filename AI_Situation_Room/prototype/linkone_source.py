"""Bounded read-only Postgres intake over a pinned, process-owned SSH tunnel.

The app delegates to its existing private psycopg environment. No credentials
are passed in command arguments, HTTP responses or error messages.
"""
import json
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from .linkone_access import PRIVATE, HOST_FINGERPRINT, private_file
from .linkone_data import COLUMNS, MAX_BYTES, MAX_ROWS, room_uuid, project_payload

ROOT=Path(__file__).resolve().parents[1]


class Source:
    def __init__(self):
        self.lock=threading.Lock();self.last_finished=0

    def _run(self,action,room=None):
        with self.lock:
            time.sleep(max(0,5-(time.monotonic()-self.last_finished)))
            python=PRIVATE/'venv'/'bin'/'python'
            if not python.is_file():raise RuntimeError('Link-One runtime unavailable')
            args=[str(python),'-m','prototype.linkone_source',action]
            if room:args.append(room_uuid(room))
            proc=subprocess.Popen(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            try:
                stdout,_=proc.communicate(timeout=240)
                if proc.returncode or len(stdout)>MAX_BYTES:raise RuntimeError('Source unavailable or oversized')
                return json.loads(stdout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGTERM);proc.communicate(timeout=5)
                raise RuntimeError('Source timeout') from None
            finally:self.last_finished=time.monotonic()

    def rooms(self):return self._run('rooms')
    def fetch(self,room):return self._run('fetch',room)


def revision(room):
    try:
        response=subprocess.run(['/usr/bin/curl','--fail','--silent','--show-error','--proto','=https',
            '--connect-timeout','5','--max-time','10','https://114-110-181-118.sslip.io/api/sync?rooms='+room],
            capture_output=True,check=True,text=True,timeout=12)
        data=json.loads(response.stdout)
        return {'all':data['all'],'rooms':{room:data['rooms'][room]}}
    except Exception:return {'unavailable':True}


@contextmanager
def connection(statement_timeout=15000):
    """One pinned tunnel and read-only connection; callers own short transactions."""
    import psycopg
    from psycopg.rows import dict_row
    key=private_file(Path.home()/'.ssh'/'haeon_linkone_ed25519')
    hosts=private_file(PRIVATE/'known_hosts')
    fingerprint=subprocess.run(['/usr/bin/ssh-keygen','-lf',str(hosts),'-E','sha256'],capture_output=True,text=True,check=True).stdout.split()[1]
    if fingerprint!=HOST_FINGERPRINT:raise ValueError('Host key mismatch')
    password=private_file(PRIVATE/'db_password').read_text().strip()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    args=['/usr/bin/ssh','-F','/dev/null','-N','-p','10022','-i',str(key),
          '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',
          '-o','UserKnownHostsFile='+str(hosts),'-o','GlobalKnownHostsFile=/dev/null',
          '-o','HostKeyAlgorithms=ssh-ed25519','-o','ExitOnForwardFailure=yes',
          '-o','ConnectTimeout=10','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=2',
          '-L',f'127.0.0.1:{port}:127.0.0.1:5432','linkone-link@114.110.181.118']
    tunnel=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+15
        while True:
            if tunnel.poll() is not None:raise RuntimeError('SSH stopped')
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.3):break
            except OSError:
                if time.monotonic()>deadline:raise RuntimeError('SSH timeout')
                time.sleep(.1)
        with psycopg.connect(host='127.0.0.1',port=port,dbname='linkone',user='linkone_ro',password=password,
            sslmode='disable',connect_timeout=10,row_factory=dict_row,autocommit=True,
            application_name='haeon-linkone-readonly',
            options=f'-c default_transaction_read_only=on -c statement_timeout={int(statement_timeout)}') as conn:
            yield conn
    finally:
        tunnel.terminate()
        try:tunnel.wait(timeout=5)
        except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()



def receive(action,room=None):
    from psycopg import sql
    with connection() as conn:
        before=revision(room) if room else {}
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                if action=='rooms':
                    cur.execute('SELECT id,name,case_no,mode,status,ship_name,created_at FROM public.room ORDER BY created_at DESC LIMIT 1000')
                    rows=cur.fetchall()
                    if len(rows)==1000:raise ValueError('Room list limit reached')
                    return rows
                data={};size=0
                for table,columns in COLUMNS.items():
                    rows=[];last=None;pk='person_id' if table=='person_state' else 'id'
                    where='id' if table=='room' else 'room_id'
                    while True:
                        # One manual intake reads its pages consecutively; _run spaces intakes.
                        query=sql.SQL('SELECT {} FROM public.{} WHERE {}=%s').format(
                            sql.SQL(',').join(map(sql.Identifier,columns.split())),sql.Identifier(table),sql.Identifier(where))
                        params=[room]
                        if last is not None:
                            query+=sql.SQL(' AND {}>%s').format(sql.Identifier(pk));params.append(last)
                        query+=sql.SQL(' ORDER BY {} LIMIT 1000').format(sql.Identifier(pk))
                        cur.execute(query,params);page=cur.fetchall()
                        if page:last=page[-1][pk]
                        # Preserve bigint IDs in JavaScript without rounding.
                        for row in page:
                            if table=='person_event':row['payload']=project_payload(row.get('type'),row.get('payload',{}))
                            for k,v in list(row.items()):
                                if type(v) is int and (k=='id' or k.endswith('_id')):row[k]=str(v)
                        rows.extend(page);size+=len(json.dumps(page,default=str,ensure_ascii=False).encode())
                        if len(rows)>MAX_ROWS or size>MAX_BYTES-100000:raise ValueError('Snapshot limit reached')
                        if len(page)<1000:break
                    data[table]=rows
    return dict(room_id=room,data=data,received_at=time.time(),complete=True,
                    revisions={'before':before,'after':revision(room)})

def main():
    try:
        action=sys.argv[1]
        if action not in ('rooms','fetch'):raise ValueError('action')
        room=room_uuid(sys.argv[2]) if action=='fetch' else None
        print(json.dumps(receive(action,room),ensure_ascii=False,default=str,allow_nan=False))
    except Exception:
        print('Link-One read failed; credentials and source payload omitted.',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
