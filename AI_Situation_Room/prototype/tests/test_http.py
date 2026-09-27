import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from prototype.store import Store
from prototype.engine import Engine
from prototype.models import DemoModel
try:
    from prototype.server import make_server
except ImportError:
    make_server=None


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(make_server, 'HTTP API is not implemented')
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'db.sqlite')
        self.engine=Engine(self.store,demo_model=DemoModel(delay=.001))
        self.server=make_server(self.store,self.engine,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.token=self.request('/api/config')[1]['token']
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown(); self.server.server_close(); self.engine.close(); self.tmp.cleanup()

    def request(self,path,data=None,headers=None):
        req=urllib.request.Request(self.base+path, data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type':'application/json','X-Session-Token':getattr(self,'token',''),**(headers or {})})
        try:
            with urllib.request.urlopen(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as exc:return exc.code,json.load(exc)

    def test_origin_and_write_token_enforced(self):
        self.assertEqual(self.request('/api/sessions',{'title':'X','mode':'demo'}, {'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/sessions',{'title':'X','mode':'demo'}, {'X-Session-Token':'wrong'})[0],403)
        self.assertEqual(self.store.list_sessions(),[])

    def test_session_input_and_snapshot_do_not_create_jobs(self):
        status,s=self.request('/api/sessions',{'title':'A','mode':'demo'})
        self.assertEqual(status,201)
        for _ in range(3):
            code,snap=self.request('/api/sessions/'+s['id'])
            self.assertEqual(code,200);self.assertEqual(snap['runs'],[])
        self.assertEqual(self.request('/api/sessions/missing')[0],404)
        self.assertEqual(self.request('/api/sessions',{'title':'','mode':'demo'})[0],400)

    def test_message_roundtrip_and_monitor_write_rejected(self):
        _,s=self.request('/api/sessions',{'title':'A','mode':'demo'})
        path='/api/sessions/'+s['id']
        payload={'prompt':'정리해줘','kind':'analysis','assumptions':'','request_id':'id'}
        code,r=self.request(path+'/message',payload)
        self.assertEqual(code,202)
        self.engine.wait(r['id'])
        self.assertEqual(self.request(path+'/message',payload)[1]['id'],r['id'])
        self.assertEqual(len(self.request(path)[1]['messages']),2)
        self.assertEqual(self.request('/api/monitor/message',payload)[0],404)

    def test_inbox_local_approval_and_session_guard(self):
        from prototype.inbox import Inbox
        _, s = self.request('/api/sessions', {'title':'A호','mode':'demo'})
        _, other = self.request('/api/sessions', {'title':'B호','mode':'demo'})
        path = '/api/sessions/'+s['id']
        self.assertEqual(self.request(path+'/inbox-link', {'project':'link-one','incident_id':'a'})[0],200)
        report = Inbox(self.store).receive('link-one', dict(report_id='1', incident_id='a',incident_title='A호',
                        reported_at='2026-09-27T14:32:00+09:00', content='구조자 상태 변화'))
        self.assertEqual(self.request('/api/inbox')[1]['reports'][0]['id'],report['id'])
        payload = {'inbox_report_id':report['id']}
        self.assertEqual(self.request('/api/sessions/'+other['id']+'/message',payload)[0],409)
        self.assertEqual(self.request(path+'/message',payload,{'X-Session-Token':'invalid'})[0],403)
        status, run = self.request(path+'/message',payload)
        self.assertEqual(status,202)
        self.engine.wait(run['id'])
        self.assertEqual(self.request(path+'/message',payload)[1]['id'],run['id'])
        self.assertEqual(len(self.store.snapshot(s['id'])['runs']),1)
