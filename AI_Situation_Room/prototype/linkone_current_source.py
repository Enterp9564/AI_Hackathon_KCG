"""Bounded read-only current-state worker; RECORD intake does not wait for AI."""
import json
import sys
from .linkone_current import FIELDS, MAX_ROWS, MAX_BYTES, normalize_current
from .linkone_data import room_uuid
from .linkone_source import connection

RECORDS='''WITH ranked AS (
 SELECT e.id,e.room_id,e.person_id,e.server_at,e.client_at,
 jsonb_build_object('text',e.payload->'text','category',e.payload->'category','via',e.payload->'via') AS payload,
 row_number() OVER (PARTITION BY e.room_id,e.person_id ORDER BY e.server_at DESC,e.id DESC) AS rank,
 count(*) OVER (PARTITION BY e.room_id,e.person_id) AS total
 FROM public.person_event e WHERE e.room_id=ANY(%s::uuid[]) AND e.type::text='RECORD'
), selected AS (SELECT * FROM ranked WHERE rank<=5 ORDER BY room_id,person_id,rank LIMIT 2001)
SELECT r.id::text,r.room_id,r.person_id,r.server_at,r.client_at,r.payload,r.total,
 EXISTS(SELECT 1 FROM public.person_event u WHERE u.room_id=r.room_id AND u.person_id=r.person_id
 AND u.type::text='UNDO' AND (u.undo_of=r.id OR u.payload->>'eventId'=r.id::text)) AS canceled
FROM selected r'''


def read_current_poll(conn,rooms,known):
    from psycopg import sql
    rooms=sorted(set(room_uuid(r) for r in rooms))
    if not rooms or len(rooms)>32:raise ValueError('room limit')
    data={r:{**{t:[] for t in FIELDS},'recent_records':[],'record_totals':{}} for r in rooms}
    size=0
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            for table,fields in FIELDS.items():
                cur.execute(sql.SQL('SELECT {} FROM public.{} WHERE {}=ANY(%s::uuid[]) ORDER BY {} LIMIT 2001').format(
                    sql.SQL(',').join(map(sql.Identifier,fields)),sql.Identifier(table),
                    sql.Identifier('id' if table=='room' else 'room_id'),sql.Identifier('person_id' if table=='person_state' else 'id')),(rooms,))
                rows=cur.fetchall()
                if len(rows)>MAX_ROWS:raise ValueError('row limit')
                for row in rows:
                    # Stringify bigint IDs before JSON; UUID/datetime serialization matches manual intake.
                    row={k:str(v) if type(v) is int and (k=='id' or k.endswith('_id')) else v for k,v in row.items()}
                    row=json.loads(json.dumps(row,default=str,ensure_ascii=False,allow_nan=False))
                    size+=len(json.dumps(row,ensure_ascii=False).encode())
                    if size>MAX_BYTES:raise ValueError('size limit')
                    r=row['id' if table=='room' else 'room_id'];data[r][table].append(row)
            for r,d in data.items():d['record_totals']={p['id']:0 for p in d['person']}
            cur.execute(RECORDS,(rooms,));records=cur.fetchall()
            if len(records)>MAX_ROWS:raise ValueError('record limit')
            for record in records:
                row=json.loads(json.dumps(record,default=str,ensure_ascii=False,allow_nan=False))
                r=row['room_id'];total=row.pop('total');data[r]['record_totals'][row['person_id']]=total
                data[r]['recent_records'].append(row)
            result={}
            for r,d in data.items():
                normalized=normalize_current(d,r);fingerprint=normalized['fingerprint']
                result[r]={'fingerprint':fingerprint,'data':None if known.get(r)==fingerprint else d}
            if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode())>MAX_BYTES:raise ValueError('response limit')
            return result


def main():
    try:
        with connection(statement_timeout=1500) as conn:
            for line in sys.stdin:
                if len(line)>20000:raise ValueError('request limit')
                request=json.loads(line)
                result=read_current_poll(conn,request['rooms'],request.get('known',{}))
                print(json.dumps(result,ensure_ascii=False,allow_nan=False),flush=True)
    except Exception:
        print('{"error":true}',flush=True);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
