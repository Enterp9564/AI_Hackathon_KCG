"""Display-only Link-One state; never mutates facts, runs or analysis snapshots."""
import copy
import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from .linkone_data import COLUMNS, room_uuid, person_summary
from .store import encode

MAX_ROWS=2000
MAX_BYTES=2_000_000
FIELDS={t:COLUMNS[t].split() for t in ('room','person','person_state','closure_place')}
EVENT_FIELDS='id room_id person_id server_at client_at'.split()
ERROR='현재 상태 수신 지연 · 마지막 정상 자료를 유지합니다.'


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def project_snapshot(data, room_id):
    """Project an immutable full snapshot to exactly the same display contract."""
    result={t:[{k:r.get(k) for k in keys} for r in data.get(t,[])] for t,keys in FIELDS.items()}
    events=data.get('person_event',[]);records=[];totals={p['id']:0 for p in result['person']}
    undos={str(e.get('undo_of') or e.get('payload',{}).get('eventId')) for e in events if e.get('type')=='UNDO'}
    for p in result['person']:
        rows=[e for e in events if e.get('type')=='RECORD' and e.get('person_id')==p['id']]
        totals[p['id']]=len(rows)
        rows.sort(key=lambda e:(str(e.get('server_at') or ''),int(e['id'])),reverse=True)
        for e in rows[:5]:
            record={k:e.get(k) for k in EVENT_FIELDS}
            record.update(payload={k:e.get('payload',{}).get(k) for k in ('text','category','via')},
                          canceled=str(e['id']) in undos)
            records.append(record)
    result.update(recent_records=records,record_totals=totals)
    return result


def normalize_current(payload,room_id):
    room_id=room_uuid(room_id)
    if not isinstance(payload,dict) or set(payload)!=set(FIELDS)|{'recent_records','record_totals'}:raise ValueError('current fields')
    if len(encode(payload).encode())>MAX_BYTES:raise ValueError('current size')
    result=copy.deepcopy(payload)
    for table,keys in FIELDS.items():
        rows=result[table]
        if not isinstance(rows,list) or len(rows)>MAX_ROWS:raise ValueError('current rows')
        seen=set();pk='person_id' if table=='person_state' else 'id'
        for row in rows:
            if not isinstance(row,dict) or set(row)-set(keys):raise ValueError('current columns')
            if row.get('id' if table=='room' else 'room_id')!=room_id:raise ValueError('current room')
            ident=row.get(pk)
            if not isinstance(ident,str) or not ident or ident in seen:raise ValueError('current identity')
            seen.add(ident)
            for key in keys:row.setdefault(key,None)
        rows.sort(key=lambda r:r[pk])
    if len(result['room'])!=1:raise ValueError('missing room')
    people={p['id'] for p in result['person']}
    if any(s['person_id'] not in people for s in result['person_state']):raise ValueError('current person ref')
    records=result['recent_records'];totals=result['record_totals']
    if not isinstance(records,list) or len(records)>MAX_ROWS or not isinstance(totals,dict) or set(totals)!=people:raise ValueError('record scope')
    counts={p:0 for p in people};ids=set()
    for r in records:
        if set(r)!=set(EVENT_FIELDS)|{'payload','canceled'}:raise ValueError('record fields')
        if r['room_id']!=room_id or r['person_id'] not in people:raise ValueError('record reference')
        if not isinstance(r['id'],str) or not r['id'].isdigit() or r['id'] in ids:raise ValueError('record identity')
        if type(r['canceled']) is not bool:raise ValueError('record cancellation')
        if not isinstance(r['payload'],dict) or set(r['payload'])-{'text','category','via'}:raise ValueError('record payload')
        if any(v is not None and not isinstance(v,str) for v in r['payload'].values()):raise ValueError('record text')
        r['payload']={k:r['payload'].get(k) for k in ('text','category','via')}
        ids.add(r['id']);counts[r['person_id']]+=1
    if any(type(totals[p]) is not int or totals[p]<counts[p] or counts[p]>5 or counts[p]!=min(5,totals[p]) for p in people):raise ValueError('record completeness')
    # Align timestamp spellings between full snapshots and periodic PostgreSQL reads.
    def dates(v):
        if isinstance(v,dict):
            for k,x in v.items():
                if k.endswith('_at') and isinstance(x,str):
                    try:v[k]=datetime.fromisoformat(x.replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
                    except ValueError:pass
                else:dates(x)
        elif isinstance(v,list):
            for x in v:dates(x)
    dates(result)
    records.sort(key=lambda r:(r.get('server_at') or '',int(r['id'])),reverse=True)
    fingerprint=hashlib.sha256(canonical(result).encode()).hexdigest()
    updated=[s.get('updated_at') for s in result['person_state']]+[r.get('server_at') for r in records]
    return dict(result,fingerprint=fingerprint,summary=person_summary(result['room'][0],result['person'],result['person_state']),
        source_updated_at=max((v for v in updated if v),default=None),records_omitted=sum(totals.values())-len(records))


class CurrentSituation:
    def __init__(self,store,source=None,interval=3,start=True):
        if interval not in (0,3):raise ValueError('current interval')
        from .linkone_alert_source import AlertSource
        self.store=store;self.source=source or AlertSource(worker_module='prototype.linkone_current_source')
        self.interval=interval;self.states={};self.known={};self.targets={};self.failures=0;self.basis={}
        self.lock=threading.RLock();self.poll_lock=threading.Lock();self.stop=threading.Event();self.thread=None
        with store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS linkone_current_cache (session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE, room_id TEXT NOT NULL, data TEXT NOT NULL)')
        if start:self.start()

    def start(self):
        if not self.interval or self.thread:return
        self.thread=threading.Thread(target=self._loop,daemon=True,name='linkone-current');self.thread.start()

    def _loop(self):
        while not self.stop.is_set():
            began=time.monotonic();delay=self.tick();elapsed=time.monotonic()-began
            self.stop.wait(max(.1,delay-elapsed) if elapsed<delay else delay)

    def tick(self):
        if not self.interval:return 3
        if not self.poll_lock.acquire(False):return self.interval
        try:return self._tick()
        finally:self.poll_lock.release()

    def _tick(self):
        targets={s['id']:s['linkone']['room_id'] for s in self.store.list_sessions() if s.get('linkone',{}).get('room_id')}
        rooms=sorted(set(targets.values()));began=time.time()
        with self.lock:
            for sid,room in targets.items():
                if self.targets.get(sid)!=room:self.known.pop(room,None)
            self.targets=targets;self.states={s:v for s,v in self.states.items() if s in targets}
            self.known={r:v for r,v in self.known.items() if r in rooms}
            known=dict(self.known)
        if not rooms:self.source.close();self.failures=0;return 3
        try:
            if len(rooms)>32:raise ValueError('room limit')
            response=self.source.poll(rooms,known)
            if set(response)!=set(rooms) or len(encode(response).encode())>MAX_BYTES:raise ValueError('incomplete response')
            cleaned={}
            for room,p in response.items():
                if not isinstance(p.get('fingerprint'),str):raise ValueError('fingerprint')
                if p.get('data') is None:
                    if known.get(room)!=p['fingerprint']:raise ValueError('missing detail')
                else:
                    cleaned[room]=normalize_current(p['data'],room)
                    if cleaned[room]['fingerprint']!=p['fingerprint']:raise ValueError('fingerprint mismatch')
            if any(sum(len(p[k]) for p in cleaned.values())>MAX_ROWS for k in ('person','recent_records')):raise ValueError('row limit')
            now=time.time()
            with self.lock,self.store.db() as db:
                for sid,room in targets.items():
                    try:s=self.store._session(db,sid)
                    except KeyError:continue
                    if s.get('linkone',{}).get('room_id')!=room:continue
                    old=db.execute('SELECT data FROM linkone_current_cache WHERE session_id=? AND room_id=?',(sid,room)).fetchone()
                    previous=json.loads(old[0]) if old else None
                    if room in cleaned:
                        data=cleaned[room]
                        if not previous or previous['fingerprint']!=data['fingerprint']:
                            saved=dict(data,received_at=now,room_id=room)
                            self.store._add(db,sid,'linkone_current_snapshots',saved)
                            db.execute('INSERT OR REPLACE INTO linkone_current_cache VALUES(?,?,?)',(sid,room,encode(saved)))
                    elif not previous:
                        self.known.pop(room,None);continue
                    self.states[sid]=dict(status='ready',checked_at=now,queried_at=began,next_check_at=now+3,error=None)
                self.known.update({r:p['fingerprint'] for r,p in response.items() if r in cleaned or r in self.known})
            self.failures=0;return 3
        except Exception:
            self.source.close();self.failures+=1;delay=min(60,3*2**min(self.failures,5))
            with self.lock:
                self.known.clear()
                for sid in targets:
                    self.states[sid]=dict(self.states.get(sid,{}),status='error',error=ERROR,next_check_at=time.time()+delay)
            return delay

    def view(self,sid,details=False):
        with self.lock,self.store.db() as db:
            s=self.store._session(db,sid);link=s.get('linkone') or {};room=link.get('room_id')
            row=db.execute('SELECT data FROM linkone_current_cache WHERE session_id=? AND room_id=?',(sid,room)).fetchone()
            cached=json.loads(row[0]) if row else None
            state=dict(self.states.get(sid,{}) if self.targets.get(sid)==room else {})
            status='disabled' if not self.interval else state.get('status','waiting') if room else 'unlinked'
            basis_id=link.get('snapshot_id');matches=None
            if cached and basis_id:
                if basis_id not in self.basis:
                    try:
                        snap=self.store._object(db,basis_id,sid,'linkone_snapshots')
                        self.basis={basis_id:normalize_current(project_snapshot(snap['data'],room),room)['fingerprint']}
                    except (KeyError,ValueError,TypeError):self.basis={basis_id:None}
                if self.basis.get(basis_id):matches=cached['fingerprint']==self.basis[basis_id]
            stale=bool(cached) and (status!='ready' or time.time()-state.get('checked_at',0)>10)
            superseded=bool(cached and link.get('last_received_at',0)>(state.get('queried_at') or cached['received_at']))
            out=dict(session_id=sid,room_id=room,linked=bool(room),status=status,interval_seconds=self.interval,
                checked_at=state.get('checked_at'),received_at=cached['received_at'] if cached else None,
                source_updated_at=cached.get('source_updated_at') if cached else None,
                fingerprint=cached['fingerprint'] if cached else None,summary=cached['summary'] if cached else None,
                stale=stale,superseded=superseded,basis_matches=matches,basis_snapshot_id=basis_id,basis_revision=link.get('revision'),
                error=state.get('error'),next_check_at=state.get('next_check_at'))
            if details and cached:
                for key in ('person','person_state','closure_place','recent_records','record_totals','records_omitted'):out[key]=cached[key]
            return out

    def close(self):
        self.stop.set()
        if hasattr(self.source,'shutdown'):self.source.shutdown()
        else:self.source.close()
        if self.thread:self.thread.join(timeout=3)
