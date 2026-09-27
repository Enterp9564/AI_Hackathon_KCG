"""External claims stay outside the incident ledger until a human requests review."""
import json
import time
from datetime import datetime
from .store import Conflict, encode, text, uid

PROJECTS = {'link-one': 'Link-One', 'resaid-ai': 'RESAID AI'}
FIELDS = {'report_id': 120, 'incident_id': 120, 'incident_title': 200,
          'reported_at': 64, 'content': 6000}


class Inbox:
    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS incident_links (
                    project TEXT NOT NULL, incident_id TEXT NOT NULL,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    PRIMARY KEY(project,incident_id));
                CREATE TABLE IF NOT EXISTS inbox_reports (
                    id TEXT PRIMARY KEY, project TEXT NOT NULL, report_id TEXT NOT NULL,
                    session_id TEXT NOT NULL, received REAL NOT NULL, data TEXT NOT NULL,
                    UNIQUE(project,report_id));
            ''')

    @staticmethod
    def project(project):
        if project not in PROJECTS:
            raise ValueError('지원하지 않는 프로젝트입니다.')
        return project

    def link(self, sid, project, incident_id):
        project, incident_id = self.project(project), text(incident_id, 120)
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.store._session(db, sid)
            prior = db.execute('SELECT session_id FROM incident_links WHERE project=? AND incident_id=?',
                               (project, incident_id)).fetchone()
            if prior and prior[0] != sid:
                raise Conflict('이 외부 사건 ID는 다른 세션에 연결되어 있습니다. 새 사건 ID를 사용하세요.')
            db.execute('INSERT OR IGNORE INTO incident_links VALUES(?,?,?)', (project, incident_id, sid))
        return dict(project=project, incident_id=incident_id, session_id=sid)

    def list(self):
        with self.store.db() as db:
            reports = [json.loads(r[0]) for r in db.execute('SELECT data FROM inbox_reports ORDER BY received DESC,id')]
            links = [dict(project=r[0], incident_id=r[1], session_id=r[2]) for r in db.execute('SELECT * FROM incident_links')]
        return dict(reports=reports, links=links, projects=PROJECTS)

    def _get(self, db, report_id):
        row = db.execute('SELECT data FROM inbox_reports WHERE id=?', (report_id,)).fetchone()
        if not row:
            raise KeyError('수신 보고를 찾을 수 없습니다.')
        return json.loads(row[0])

    def get(self, report_id):
        with self.store.db() as db:
            return self._get(db, report_id)

    def _save(self, db, report):
        db.execute('UPDATE inbox_reports SET data=? WHERE id=?', (encode(report), report['id']))

    def receive(self, project, payload):
        project = self.project(project)
        if not isinstance(payload, dict) or set(payload) != set(FIELDS):
            raise ValueError('report_id, incident_id, incident_title, reported_at, content만 필요합니다.')
        clean = {k: text(payload[k], n) for k, n in FIELDS.items()}
        stamp = datetime.fromisoformat(clean['reported_at'].replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError('보고 시각에 시간대가 필요합니다. 예: 2026-09-27T14:32:00+09:00')
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT data FROM inbox_reports WHERE project=? AND report_id=?',
                               (project, clean['report_id'])).fetchone()
            if prior:
                report = json.loads(prior[0])
                if report['original'] != payload:
                    raise Conflict('같은 report_id의 원문이 다릅니다. 정정 보고에는 새로운 ID를 사용하세요.')
                return report
            link = db.execute('SELECT session_id FROM incident_links WHERE project=? AND incident_id=?',
                              (project, clean['incident_id'])).fetchone()
            if not link:
                raise ValueError('상황실에서 이 프로젝트의 사건 ID를 먼저 연결하세요.')
            now = time.time()
            report = dict(id=uid(), project=project, session_id=link[0], original=dict(payload),
                          received_at=now, status='pending', seen_at=None, run_id=None, quote=None,
                          history=[dict(action='received', at=now)])
            db.execute('INSERT INTO inbox_reports VALUES(?,?,?,?,?,?)',
                       (report['id'], project, clean['report_id'], link[0], now, encode(report)))
            return report

    def act(self, sid, report_id, action):
        if action not in ('seen', 'later', 'reject'):
            raise ValueError('지원하지 않는 처리입니다.')
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            r = self._get(db, report_id)
            if r['session_id'] != sid:
                raise Conflict('보고의 연결 사건과 현재 사건이 다릅니다.')
            if r['status'] in ('sent', 'rejected'):
                return r
            if action == 'seen' and r['seen_at'] is not None:
                return r
            if action == 'later' and r['status'] == 'deferred':
                return r
            if action == 'seen': r['seen_at'] = time.time()
            if action == 'later': r['status'] = 'deferred'
            if action == 'reject': r['status'] = 'rejected'
            r['history'].append(dict(action=action, at=time.time()))
            self._save(db, r)
            return r

    @staticmethod
    def quote(r):
        p = r['original']
        return (f"[{PROJECTS[r['project']]} 수신 정보 인용]\n사건: {p['incident_title']}\n"
                f"외부 사건 ID: {p['incident_id']}\n보고 시각: {p['reported_at']}\n"
                f"보고 ID: {p['report_id']}\n내용: {p['content']}\n\n"
                '위 보고를 현재 상황과 함께 검토하고, 필요한 대응 제안과 추가 확인사항을 알려주세요.\n'
                '이 인용은 검토 요청이며 보고 내용의 사실 확정이 아닙니다.')

    def enqueue(self, sid, report_id):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            r = self._get(db, report_id)
            if r['session_id'] != sid:
                raise Conflict('보고의 연결 사건과 현재 사건이 다릅니다.')
            self.store._session(db, sid)
            if r['status'] == 'sent':
                return self.store._object(db, r['run_id'], sid, 'runs')
            if r['status'] == 'rejected':
                raise Conflict('반영하지 않기로 처리한 보고입니다.')
            quote = self.quote(r)
            run = self.store._enqueue(db, sid, quote, 'analysis', '', 'inbox:'+r['id'],
                                      external_report_id=r['id'])
            r.update(status='sent', seen_at=time.time(), run_id=run['id'], quote=quote)
            r['history'].append(dict(action='quote_sent', at=time.time(), run_id=run['id']))
            self._save(db, r)
            return run
