"""Durable session-scoped state. All writes are short SQLite transactions."""
import csv
import io
import json
import math
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class Conflict(ValueError):
    pass


def uid():
    return uuid.uuid4().hex


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def text(value, limit=8000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'빈 값은 허용하지 않으며 최대 {limit:,}자까지 입력할 수 있습니다.')
    return value.strip()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS objects (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    kind TEXT NOT NULL, created REAL NOT NULL, data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS objects_session ON objects(session_id,kind,created);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            ''')

    @contextmanager
    def db(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.execute('PRAGMA foreign_keys=ON')
            try:
                with db:
                    yield db
            finally:
                db.close()

    def _session(self, db, sid):
        row = db.execute('SELECT data FROM sessions WHERE id=?', (sid,)).fetchone()
        if not row:
            raise KeyError('세션을 찾을 수 없습니다.')
        return json.loads(row[0])

    def _put_session(self, db, data):
        data['updated_at'] = time.time()
        db.execute('UPDATE sessions SET data=? WHERE id=?', (encode(data), data['id']))

    def _add(self, db, sid, kind, data):
        data = dict(data, id=data.get('id', uid()), session_id=sid,
                    created_at=data.get('created_at', time.time()))
        db.execute('INSERT INTO objects VALUES(?,?,?,?,?)',
                   (data['id'], sid, kind, data['created_at'], encode(data)))
        return data

    def _items(self, db, sid, kind):
        return [json.loads(r[0]) for r in db.execute(
            'SELECT data FROM objects WHERE session_id=? AND kind=? ORDER BY created,id', (sid, kind))]

    def _object(self, db, oid, sid=None, kind=None):
        row = db.execute('SELECT session_id,kind,data FROM objects WHERE id=?', (oid,)).fetchone()
        if not row or (sid is not None and row[0] != sid) or (kind and row[1] != kind):
            raise KeyError('현재 세션의 기록을 찾을 수 없습니다.')
        return json.loads(row[2])

    def _update(self, db, oid, data):
        db.execute('UPDATE objects SET data=? WHERE id=?', (encode(data), oid))

    def create_session(self, title, mode='demo'):
        title = text(title, 80)
        if mode not in ('demo', 'live'):
            raise ValueError('지원하지 않는 실행 모드입니다.')
        data = dict(id=uid(), title=title, mode=mode, version=0, facts={},
                    created_at=time.time(), updated_at=time.time(), weather=None)
        with self.db() as db:
            db.execute('INSERT INTO sessions VALUES(?,?)', (data['id'], encode(data)))
        return data

    def delete_session(self, sid):
        """Delete one session and its session-scoped records after a safe idle check."""
        with self.db() as db:
            session=self._session(db, sid)
            if session.get('linkone',{}).get('status')=='receiving':raise Conflict('링크온 자료 수신 중에는 삭제할 수 없습니다.')
            pending = any(run.get('status') in ('queued','running') for run in self._items(db, sid, 'runs'))
            if pending:
                raise Conflict('진행 중인 지시가 있어 세션을 삭제할 수 없습니다. 작업이 끝난 뒤 다시 시도하세요.')
            db.execute('DELETE FROM objects WHERE session_id=?', (sid,))
            db.execute('DELETE FROM sessions WHERE id=?', (sid,))
            db.execute("DELETE FROM settings WHERE key='pinned' AND value=?", (sid,))
        return {'id':sid, 'deleted':True}

    def list_sessions(self):
        with self.db() as db:
            return sorted([json.loads(r[0]) for r in db.execute('SELECT data FROM sessions')],
                          key=lambda s: s['created_at'], reverse=True)

    def snapshot(self, sid):
        with self.db() as db:
            session = self._session(db, sid)
            result = {'session': session}
            for kind in ('messages', 'runs', 'tasks', 'events', 'attachments', 'calls'):
                result[kind] = self._items(db, sid, kind)
            result['manual_contexts']=[{k:v for k,v in record.items() if k!='items'}
                                      for record in self._items(db,sid,'manual_contexts')]
            for kind in ('runs', 'tasks', 'messages'):
                for item in result[kind]:
                    if item.get('status') == 'completed' and item.get('based_on_version') != session['version']:
                        item['status'] = 'stale'
            from .manuals import resource_scope
            result['resource_scope']=resource_scope(session)
            if session.get('linkone',{}).get('snapshot_id'):
                from .linkone_data import evidence
                result['linkone_evidence']=evidence(self._object(db,session['linkone']['snapshot_id'],sid,'linkone_snapshots'))
            result['server_time'] = time.time()
            return result

    def set_facts(self, sid, facts, expected_version):
        if not isinstance(facts, dict) or set(facts) - {'total', 'rescued', 'remaining', 'location', 'lat', 'lon', 'notes'}:
            raise ValueError('지원하지 않는 상황 항목입니다.')
        clean = {}
        for k, v in facts.items():
            if v is None or v == '':
                continue
            if k in ('total', 'rescued', 'remaining'):
                if type(v) is not int or not 0 <= v <= 100000:
                    raise ValueError('인원은 0 이상의 정수여야 합니다.')
            elif k in ('lat', 'lon'):
                bound = 90 if k == 'lat' else 180
                if type(v) not in (float, int) or not math.isfinite(v) or abs(v) > bound:
                    raise ValueError('좌표 범위를 확인하세요.')
            else:
                v = text(v, 2000)
            clean[k] = v
        if clean.get('rescued', 0) > clean.get('total', 100000):
            raise ValueError('구조 보고 인원이 총원보다 많습니다.')
        with self.db() as db:
            session = self._session(db, sid)
            if session.get('linkone'):raise Conflict('링크온 원본 집계는 동기화로만 변경할 수 있습니다.')
            if type(expected_version) is not int or session['version'] != expected_version:
                raise Conflict('상황이 갱신되었습니다. 최신 값을 확인하고 다시 반영하세요.')
            before = session['facts']
            if 'remaining' not in facts and 'remaining' in before:
                clean['remaining']=before['remaining']
            from .incident import merge_update
            merge_update(dict(session,facts=clean),{})
            if any(before.get(k) != clean.get(k) for k in ('lat','lon')):
                if session.get('weather'):
                    self._add(db, sid, 'events', {'type':'weather_invalidated','label':'위치 변경 · 기존 기상 해제','previous_weather':session['weather']})
                session['weather'] = None
            session.update(facts=clean, version=session['version'] + 1, facts_source='사용자 입력·정정')
            self._put_session(db, session)
            self._add(db, sid, 'events', {'type': 'facts_updated', 'label': '사용자 상황 반영',
                'before': before, 'after': clean, 'version': session['version']})
            return session

    def apply_update(self, rid, patch, expected_version):
        from .incident import merge_update
        with self.db() as db:
            run=self._object(db,rid,kind='runs');sid=run['session_id']
            if run.get('external_report_id'):
                raise Conflict('외부 보고 인용은 사실 확정이 아닙니다. 확인한 상황은 직접 반영하세요.')
            session=self._session(db,sid)
            if session.get('linkone'):raise Conflict('AI는 링크온 원본을 변경할 수 없습니다.')
            if run.get('update_applied'):
                if run.get('applied_patch') != patch:raise Conflict('이미 반영된 요청에 다른 갱신입니다.')
                return session
            if run['kind']=='simulation':raise ValueError('시뮬레이션 가정은 현재 상황을 변경할 수 없습니다.')
            if session['version']!=expected_version:raise Conflict('검토 중 상황이 변경됐습니다. 최신 상태로 다시 요청하세요.')
            after=merge_update(session,patch)
            import re
            stamp=re.match(r'^\s*((?:[01]?\d|2[0-3]):[0-5]\d)\b',run['prompt'])
            if stamp:after.setdefault('incident',{})['report_time']=stamp.group(1)
            before={'facts':session['facts'],'incident':session.get('incident',{})}
            source=next(m for m in self._items(db,sid,'messages') if m.get('run_id')==rid and m['role']=='user')
            changed=after['facts']!=session['facts'] or after.get('incident',{})!=session.get('incident',{})
            if changed:
                after.update(version=session['version']+1,facts_source='사용자 신고·정정 (원문 기록)')
                if any(after['facts'].get(k)!=session['facts'].get(k) for k in ('lat','lon','location')):after['weather']=None
                self._put_session(db,after)
                self._add(db,sid,'events',dict(type='incident_updated',label='신고 반영 · 상황 S'+str(after['version']),
                    source_id=source['id'],run_id=rid,before=before,after={'facts':after['facts'],'incident':after.get('incident',{})},patch=patch))
            run.update(update_applied=True,applied_patch=patch,based_on_version=after['version'],source_id=source['id'])
            self._update(db,rid,run)
            return after

    def enqueue(self, sid, content, kind, assumptions, request_id):
        content, request_id = text(content), text(request_id, 120)
        if request_id.startswith('inbox:'):
            raise ValueError('inbox: 요청 ID는 외부 보고 승인 전용입니다.')
        if kind not in ('analysis', 'simulation'):
            raise ValueError('지원하지 않는 요청 유형입니다.')
        assumptions = text(assumptions, 3000) if kind == 'simulation' else ''
        with self.db() as db:
            return self._enqueue(db, sid, content, kind, assumptions, request_id)

    def _enqueue(self, db, sid, content, kind, assumptions, request_id, external_report_id=None):
        session = self._session(db, sid)
        if session.get('linkone',{}).get('status')=='receiving':raise Conflict('자료 수신 완료 후 지시를 보내세요.')
        for previous in self._items(db, sid, 'runs'):
            if previous['request_id'] == request_id:
                if (previous['prompt'], previous['kind'], previous['assumptions']) != (content, kind, assumptions):
                    raise Conflict('같은 요청 ID에 다른 내용이 전달되었습니다.')
                return previous
        pending = [r for r in self._items(db, sid, 'runs') if r['status'] in ('queued', 'running')]
        if len(pending) >= 8:
            raise Conflict('대기 중인 요청이 많습니다. 현재 작업 후 다시 보내주세요.')
        run = self._add(db, sid, 'runs', dict(request_id=request_id, prompt=content, kind=kind,
            assumptions=assumptions, status='queued', based_on_version=session['version'],
            linkone_snapshot_id=session.get('linkone',{}).get('snapshot_id'),
            external_report_id=external_report_id, mode=session['mode'], started_at=None, ended_at=None, decision=None, final=None, error=None))
        self._add(db, sid, 'messages', dict(role='user', content=content, run_id=run['id'],
            kind=kind, assumptions=assumptions, external_report_id=external_report_id))
        self._add(db, sid, 'events', dict(type='received', label='사용자 지시 접수', run_id=run['id']))
        return run

    def get_run(self, rid, sid=None):
        with self.db() as db:
            return self._object(db, rid, sid, 'runs')

    def update_run(self, rid, **fields):
        with self.db() as db:
            run = self._object(db, rid, kind='runs')
            run.update(fields)
            self._update(db, rid, run)
            return run

    def event(self, sid, label, event_type='progress', **data):
        with self.db() as db:
            self._session(db, sid)
            return self._add(db, sid, 'events', dict(data, label=label, type=event_type))

    def add_task(self, run, role, instruction, reason):
        with self.db() as db:
            return self._add(db, run['session_id'], 'tasks', dict(run_id=run['id'], role=role,
                instruction=instruction, reason=reason, status='assigned', started_at=None,
                ended_at=None, report=None, error=None, based_on_version=run['based_on_version'], external_report_id=run.get('external_report_id')))

    def update_task(self, tid, **fields):
        with self.db() as db:
            task = self._object(db, tid, kind='tasks')
            task.update(fields)
            self._update(db, tid, task)
            return task

    def record_call(self, sid, **fields):
        with self.db() as db:
            self._session(db, sid)
            return self._add(db, sid, 'calls', fields)

    def record_manual_context(self, sid, rid, stage, role, search_record, items):
        with self.db() as db:
            run=self._object(db,rid,sid=sid,kind='runs')
            record=self._add(db,sid,'manual_contexts',dict(run_id=rid,stage=stage,role=role,
                search=search_record,items=items,
                evidence=[{'id':e['id'],'title':e['title'],'source_title':e['source_title'],
                           'pdf_pages':e['pdf_pages']} for e in items]))
            run.setdefault('manual_context_ids',[]).append(record['id'])
            self._update(db,rid,run)
            return record['id']

    def get_manual_context(self, sid, rid, context_id):
        with self.db() as db:
            self._session(db,sid)
            self._object(db,rid,sid=sid,kind='runs')
            record=self._object(db,context_id,sid=sid,kind='manual_contexts')
            if record['run_id']!=rid:raise KeyError('현재 실행의 매뉴얼 근거가 아닙니다.')
            return record

    def finish_run(self, rid, final, status='completed', error=None):
        with self.db() as db:
            run = self._object(db, rid, kind='runs')
            session = self._session(db, run['session_id'])
            if status == 'completed' and run['based_on_version'] != session['version']:
                status = 'stale'
            run.update(final=final, status=status, error=error, ended_at=time.time())
            self._update(db, rid, run)
            if final:
                self._add(db, run['session_id'], 'messages', dict(role='commander', run_id=rid,
                    content=final['summary'], report=final, status=status, kind=run['kind'],
                    based_on_version=run['based_on_version'], external_report_id=run.get('external_report_id'),
                    external_report_ids=final.get('external_report_ids',[])))
            self._add(db, run['session_id'], 'events', dict(type='final', run_id=rid,
                label='최종 보고 전달' if status == 'completed' else '작업 결과: ' + status))
            self._put_session(db, session)
            return run

    def add_attachment(self, sid, name, content):
        name, content = text(name, 120), text(content, 100000)
        suffix = Path(name).suffix.lower()
        if suffix not in ('.csv', '.txt', '.md'):
            raise ValueError('CSV, TXT, MD 파일을 지원합니다.')
        summary = {}
        if suffix == '.csv':
            rows = list(csv.DictReader(io.StringIO(content.lstrip('\ufeff'))))
            if not rows or len(rows) > 10000 or 'id' not in rows[0] or 'rescued' not in rows[0]:
                raise ValueError('CSV에는 id,rescued 열과 1~10,000행이 필요합니다.')
            ids = [r['id'].strip() for r in rows if isinstance(r.get('id'), str)]
            if len(ids) != len(rows) or any(not i for i in ids) or len(ids) != len(set(ids)):
                raise ValueError('명부 ID가 비었거나 중복되었습니다.')
            values = [str(r.get('rescued', '')).strip().lower() for r in rows]
            if any(v not in ('true','false','1','0') for v in values):
                raise ValueError('rescued 값은 true/false 또는 1/0이어야 합니다.')
            summary = {'total': len(rows), 'rescued': sum(v in ('true','1') for v in values)}
        with self.db() as db:
            self._session(db, sid)
            result = self._add(db, sid, 'attachments', dict(name=Path(name).name,
                content=content, summary=summary, source='사용자 첨부 · 사실 확정 전'))
            self._add(db, sid, 'events', dict(type='attachment', label='자료 접수: '+result['name']))
            return result

    def set_weather(self, sid, expected_version, weather):
        with self.db() as db:
            session = self._session(db, sid)
            if session['version'] != expected_version:
                raise Conflict('조회 중 위치/상황이 변경되었습니다. 다시 조회하세요.')
            session['weather'] = weather
            session['version'] += 1
            self._put_session(db, session)
            self._add(db, sid, 'events', dict(type='weather', label='기상 조회 결과 저장'))

    def recover(self):
        with self.db() as db:
            for oid, kind, payload in db.execute("SELECT id,kind,data FROM objects WHERE kind IN ('runs','tasks')").fetchall():
                data = json.loads(payload)
                if data['status'] in ('queued','running','assigned'):
                    data.update(status='interrupted', ended_at=time.time(), error='서버가 재시작되었습니다. 새 요청으로 재검토하세요.')
                    self._update(db, oid, data)

    def pin(self, sid):
        with self.db() as db:
            self._session(db, sid)
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('pinned', sid))

    def pinned(self):
        with self.db() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', ('pinned',)).fetchone()
            return row[0] if row else None
