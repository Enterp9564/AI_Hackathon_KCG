"""Source-issued hull warnings. Never infer clearance or write acknowledgements upstream."""
import hashlib
import math
import json
import time
from datetime import datetime
from .store import encode, uid

FIELDS=('id room_id kind axis level_deg hull_tilt_id roll trim measured_at prev_roll prev_trim '
        'prev_measured_at title message basis note standard raised_at ack_count last_acked_at').split()
LIMIT=100
BASE='''WITH bounded AS (
 SELECT h.* FROM unnest(%s::uuid[]) AS r(room_id)
 CROSS JOIN LATERAL (SELECT * FROM public.hull_tilt_alert a WHERE a.room_id=r.room_id
 ORDER BY a.raised_at DESC,a.id DESC LIMIT 101) h
), projected AS (
 SELECT h.id::text,h.room_id::text,h.kind::text,h.axis::text,h.level_deg,h.hull_tilt_id::text,
 h.roll,h.trim,h.measured_at,h.prev_roll,h.prev_trim,h.prev_measured_at,
 h.title,h.message,h.basis,h.note,h.standard,h.raised_at,
 (SELECT count(*) FROM public.hull_tilt_alert_ack k WHERE k.alert_id=h.id) AS ack_count,
 (SELECT max(acked_at) FROM public.hull_tilt_alert_ack k WHERE k.alert_id=h.id) AS last_acked_at
 FROM bounded h
) '''


def read_vessel_poll(conn,rooms,known):
    # A savepoint prevents a hull-only failure from poisoning the patient transaction.
    try:
        with conn.transaction():
            with conn.cursor() as c:
                c.execute(BASE+'''SELECT room_id,count(*) AS count,
                    md5(string_agg(to_jsonb(p)::text,'' ORDER BY raised_at,id)) AS fingerprint,
                    sum(octet_length(to_jsonb(p)::text)) AS bytes FROM projected p GROUP BY room_id''',(rooms,))
                meta=c.fetchall()
                if sum(r['count'] for r in meta)>1000 or sum(r['bytes'] for r in meta)>1_000_000:raise ValueError('vessel limit')
                result={r:dict(fingerprint='empty',rows=None,truncated=False) for r in rooms}
                for row in meta:result[row['room_id']].update(fingerprint=row['fingerprint'],truncated=row['count']>LIMIT)
                changed=[r for r in rooms if known.get('vessel:'+r)!=result[r]['fingerprint']]
                if changed:
                    for r in changed:result[r]['rows']=[]
                    c.execute(BASE+'SELECT * FROM projected ORDER BY raised_at DESC,id::bigint DESC',(changed,))
                    for row in c.fetchall():
                        values=result[row['room_id']]['rows']
                        if len(values)<LIMIT:values.append(row)
                return result
    except Exception:
        return {r:dict(error=True) for r in rooms}


def normalize(rows,room):
    if not isinstance(rows,list) or len(rows)>LIMIT:raise ValueError('vessel rows')
    result=[];ids=set()
    for row in rows:
        if not isinstance(row,dict) or row.get('room_id')!=room:raise ValueError('vessel room')
        clean={k:row.get(k) for k in FIELDS}
        for key in ('id','hull_tilt_id'):
            v=clean[key]
            if v is not None and (not isinstance(v,str) or not v.isdecimal() or len(v)>20):raise ValueError('vessel id')
        if not clean['id'] or clean['id'] in ids:raise ValueError('duplicate vessel id')
        ids.add(clean['id'])
        for key in ('measured_at','prev_measured_at','raised_at','last_acked_at'):
            v=clean[key]
            if v is None and key!='raised_at':continue
            if not isinstance(v,str) or len(v)>64 or datetime.fromisoformat(v.replace('Z','+00:00')).tzinfo is None:raise ValueError('vessel time')
        for key in ('kind','axis','title','message','basis','note','standard'):
            if clean[key] is not None and not isinstance(clean[key],str):raise ValueError('vessel text')
        for key in ('level_deg','roll','trim','prev_roll','prev_trim'):
            v=clean[key]
            if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)):raise ValueError('vessel number')
        if type(clean['ack_count']) is not int or clean['ack_count']<0:raise ValueError('vessel acknowledgement')
        if len(encode(clean).encode())>24000:raise ValueError('vessel size')
        result.append(clean)
    return result


class VesselAlerts:
    def __init__(self,store):
        self.store=store;self.states={};self.known={}
        with store.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS vessel_alerts (
                id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                source_id TEXT NOT NULL,hash TEXT NOT NULL,current INTEGER NOT NULL,data TEXT NOT NULL,
                UNIQUE(session_id,source_id,hash));
                CREATE INDEX IF NOT EXISTS vessel_alert_session ON vessel_alerts(session_id,current);
                CREATE TABLE IF NOT EXISTS vessel_alert_state (
                session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,data TEXT NOT NULL);''')

    def accept(self,db,sid,room,packet,now):
        if packet is None:return
        try:
            if packet.get('error') or not isinstance(packet.get('fingerprint'),str):raise ValueError('vessel unavailable')
            rows=packet.get('rows')
            if rows is None and self.known.get(room)!=packet['fingerprint']:raise ValueError('vessel missing delta')
            rows=normalize(rows,room) if rows is not None else None
        except Exception:
            self.fail(db,sid,room);return
        if rows is not None:
            db.execute('UPDATE vessel_alerts SET current=0 WHERE session_id=?',(sid,))
            for row in rows:
                digest=hashlib.sha256(encode(row).encode()).hexdigest()
                prior=db.execute('SELECT id FROM vessel_alerts WHERE session_id=? AND source_id=? AND hash=?',(sid,row['id'],digest)).fetchone()
                if prior:db.execute('UPDATE vessel_alerts SET current=1 WHERE id=?',(prior[0],));continue
                item=dict(id=uid(),session_id=sid,original=row,received_at=now,seen_at=None)
                db.execute('INSERT INTO vessel_alerts VALUES(?,?,?,?,1,?)',(item['id'],sid,row['id'],digest,encode(item)))
        previous=self.states.get(sid,{})
        state=dict(status='ready',room_id=room,last_success_at=now,error=None,truncated=bool(packet.get('truncated')))
        if rows is not None or previous.get('status')!='ready':db.execute('INSERT OR REPLACE INTO vessel_alert_state VALUES(?,?)',(sid,encode(state)))
        self.states[sid]=state;self.known[room]=packet['fingerprint']

    def state(self,db,sid,room):
        if sid in self.states and self.states[sid].get('room_id')==room:return dict(self.states[sid])
        saved=db.execute('SELECT data FROM vessel_alert_state WHERE session_id=?',(sid,)).fetchone()
        state=json.loads(saved[0]) if saved else {}
        if state.get('room_id')!=room:state={}
        return dict(state,status='waiting',error=None)

    def fail(self,db,sid,room):
        state=self.state(db,sid,room);state.update(status='error',room_id=room,error='선체경사 경고 수신 실패 · 이전 기록 유지')
        if self.states.get(sid)!=state:db.execute('INSERT OR REPLACE INTO vessel_alert_state VALUES(?,?)',(sid,encode(state)))
        self.states[sid]=state

    def view(self,db,sid,room):
        all_rows=[(json.loads(r[0]),r[1]) for r in db.execute('SELECT data,current FROM vessel_alerts WHERE session_id=?',(sid,))]
        all_rows=[(i,current) for i,current in all_rows if i['original']['room_id']==room]
        items=[i for i,current in all_rows if current]
        ids={i['original']['id'] for i in items}
        missing={i['original']['id'] for i,current in all_rows if not current}-ids
        items.sort(key=lambda i:i['original']['raised_at'],reverse=True)
        return dict(self.state(db,sid,room),items=items,unread=sum(not i['seen_at'] for i in items),missing_count=len(missing),limit=LIMIT)

    def seen(self,sid,oid):
        with self.store.db() as db:
            s=self.store._session(db,sid)
            row=db.execute('SELECT data FROM vessel_alerts WHERE session_id=? AND id=?',(sid,oid)).fetchone()
            if not row:raise KeyError('현재 사건의 선박 경고가 없습니다.')
            item=json.loads(row[0])
            if item['original']['room_id']!=s.get('linkone',{}).get('room_id'):raise KeyError('사건이 다릅니다.')
            if not item['seen_at']:
                item['seen_at']=time.time();db.execute('UPDATE vessel_alerts SET data=? WHERE id=?',(encode(item),oid))
            return item
