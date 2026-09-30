"""Persistent, bounded, read-only alert worker. No model calls or remote writes."""
import json
import os
import select
import signal
import subprocess
import sys
import threading
import time
from .linkone_access import PRIVATE
from .linkone_data import room_uuid
from .linkone_source import ROOT, connection
from .vessel_alerts import read_vessel_poll

MAX_ROOMS=32
MAX_ROWS=1000
MAX_BYTES=2_000_000
FIELDS=('id room_id person_id status urgency summary outcomes pre_ktas reasons missing '
        'based_on_event_id based_on_at finished_at last_event_id management management_updated_at').split()

# Only explicitly selected data participates in fingerprints or crosses the tunnel.
# Current state is joined with both person and room identity.
BASE='''WITH latest AS (
 SELECT DISTINCT ON (a.room_id,a.person_id)
 a.id::text,a.room_id,a.person_id,a.status::text,a.urgency,a.summary,
 a.outcomes,a.pre_ktas,a.reasons,a.missing,a.based_on_event_id::text,a.based_on_at,a.finished_at
 FROM public.patient_ai_analysis a WHERE a.room_id=ANY(%s::uuid[])
 ORDER BY a.room_id,a.person_id,a.finished_at DESC,a.id DESC LIMIT 1001
), projected AS (
 SELECT l.*,s.last_event_id::text,s.management::text,s.updated_at AS management_updated_at FROM latest l
 LEFT JOIN public.person_state s ON s.room_id=l.room_id AND s.person_id=l.person_id
) '''
FINGERPRINT=BASE+'''SELECT room_id::text,count(*) AS count,
 md5(string_agg(to_jsonb(p)::text, '' ORDER BY person_id)) AS fingerprint,
 coalesce(sum(octet_length(to_jsonb(p)::text)),0) AS bytes
 FROM projected p GROUP BY room_id'''
DETAILS=BASE+'SELECT * FROM projected ORDER BY room_id,person_id'


def read_poll(conn,rooms,known):
    rooms=sorted(set(room_uuid(r) for r in rooms))
    if not rooms or len(rooms)>MAX_ROOMS:raise ValueError('room limit')
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            cur.execute(FINGERPRINT,(rooms,));meta=cur.fetchall()
            if sum(r['count'] for r in meta)>MAX_ROWS or sum(r['bytes'] for r in meta)>MAX_BYTES:
                raise ValueError('result limit')
            result={r:{'fingerprint':'empty','rows':None} for r in rooms}
            for row in meta:result[row['room_id']]['fingerprint']=row['fingerprint']
            changed=[r for r in rooms if known.get(r)!=result[r]['fingerprint']]
            if changed:
                for r in changed:result[r]['rows']=[]
                cur.execute(DETAILS,(changed,))
                for row in cur.fetchall():
                    row={k:str(v) if k in ('room_id','person_id') else v for k,v in row.items()}
                    result[row['room_id']]['rows'].append(row)
            vessel=read_vessel_poll(conn,rooms,known)
            for room in rooms:result[room]['vessel']=vessel[room]
            return result


class AlertSource:
    def __init__(self):
        self.proc=None;self.lock=threading.Lock();self.process_lock=threading.Lock();self.stopped=threading.Event()

    def poll(self,rooms,known):
        with self.lock:
            if self.proc and self.proc.poll() is not None:self.close()
            with self.process_lock:
                if self.stopped.is_set():raise RuntimeError('source stopped')
                if not self.proc:
                    self.proc=subprocess.Popen([str(PRIVATE/'venv/bin/python'),'-m','prototype.linkone_alert_source'],
                        cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
                proc=self.proc
            try:
                proc.stdin.write((json.dumps({'rooms':rooms,'known':known})+'\n').encode());proc.stdin.flush()
                deadline=time.monotonic()+20;data=bytearray()
                while b'\n' not in data:
                    remaining=deadline-time.monotonic()
                    if remaining<=0 or not select.select([proc.stdout],[],[],remaining)[0]:raise TimeoutError()
                    part=os.read(proc.stdout.fileno(),65536)
                    if not part:raise RuntimeError('worker stopped')
                    data.extend(part)
                    if len(data)>MAX_BYTES:raise ValueError('worker limit')
                result=json.loads(data)
                if 'error' in result:raise RuntimeError('source failed')
                return result
            except Exception:
                self.close();raise RuntimeError('Link-One alert source unavailable') from None

    def close(self):
        with self.process_lock:
            proc=self.proc;self.proc=None
        if not proc:return
        try:os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait(timeout=2)
        for stream in (proc.stdin,proc.stdout):
            if stream:stream.close()

    def shutdown(self):
        self.stopped.set();self.close()


def main():
    try:
        with connection(statement_timeout=1500) as conn:
            for line in sys.stdin:
                if len(line)>20000:raise ValueError('request limit')
                request=json.loads(line)
                result=read_poll(conn,request['rooms'],request.get('known',{}))
                encoded=json.dumps(result,ensure_ascii=False,default=str,allow_nan=False)
                if len(encoded.encode())>MAX_BYTES:raise ValueError('response limit')
                print(encoded,flush=True)
    except Exception:
        print('{"error":true}',flush=True)
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
