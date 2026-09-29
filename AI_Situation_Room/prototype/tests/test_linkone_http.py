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
from prototype.server import make_server
from prototype.tests.test_linkone_sync import Source,ROOM,OTHER


class LinkHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite')
        self.engine=Engine(self.store,demo_model=DemoModel(.001));self.source=Source()
        self.server=make_server(self.store,self.engine,0,linkone_source=self.source)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.base=f'http://127.0.0.1:{self.server.server_port}';self.token=self.request('/api/config')[1]['token']
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown();self.server.server_close();self.engine.close();self.tmp.cleanup()

    def request(self,path,data=None,token=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type':'application/json','X-Session-Token':getattr(self,'token','') if token is None else token})
        try:
            with urllib.request.urlopen(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as exc:return exc.code,json.load(exc)

    def test_auth_validation_receive_history_and_source_isolation(self):
        self.assertEqual(self.request('/api/linkone/connect',{'room_id':ROOM},'invalid')[0],403)
        self.assertEqual(self.request('/api/linkone/connect',{'room_id':'invalid'})[0],400)
        self.assertEqual(self.request('/api/linkone/rooms')[1][0]['id'],ROOM)
        code,s=self.request('/api/linkone/connect',{'room_id':ROOM,'mode':'demo'});self.assertEqual(code,202)
        sid=s['id'];path='/api/sessions/'+sid
        self.server.linkone.wait(sid);self.engine.wait(self.server.linkone.view(sid)['analysis_run_id'])
        _,d=self.request(path+'/linkone');self.assertEqual(d['summary']['total'],2)
        self.assertEqual(len(self.request(path+'/linkone-history')[1]),1)
        self.assertEqual(self.request(path+'/facts',{'facts':{'total':999},'version':1})[0],409)
        _,other=self.request('/api/linkone/connect',{'room_id':OTHER});self.server.linkone.wait(other['id'])
        self.assertEqual(self.request('/api/sessions/'+other['id']+'/linkone/'+d['id'])[0],404)
        code,r=self.request(path+'/linkone-analyze',{});self.assertEqual(code,202);self.engine.wait(r['id'])
        self.assertEqual(self.request(path+'/linkone-sync',{})[0],202);self.server.linkone.wait(sid)
        self.assertEqual(len(self.store.snapshot(sid)['runs']),2)

    def test_failed_rooms_does_not_expose_exception(self):
        def fail():raise RuntimeError('secret details')
        self.source.rooms=fail
        code,payload=self.request('/api/linkone/rooms');self.assertEqual(code,409)
        self.assertNotIn('secret',payload['error'])

    def test_body_marks_reach_http_and_ai_evidence_without_changing_raw_snapshot(self):
        from prototype.tests.test_linkone_body import marked
        from prototype.tests.test_linkone_sync import P1
        self.source.payload=marked()
        _,s=self.request('/api/linkone/connect',{'room_id':ROOM,'mode':'demo'})
        sid=s['id'];self.server.linkone.wait(sid);self.engine.wait(self.server.linkone.view(sid)['analysis_run_id'])
        code,snap=self.request('/api/sessions/'+sid+'/linkone')
        self.assertEqual(code,200)
        self.assertEqual(snap['body_locations']['people'][P1]['current'][0]['locations'][0]['label'],'우측 대퇴부')
        evidence=json.loads(self.store.snapshot(sid)['linkone_evidence']['content'])
        self.assertEqual(evidence['people'][0]['injuries']['current'][0]['locations'][0]['label'],'우측 대퇴부')
        with self.store.db() as db:
            raw=self.store._object(db,snap['id'],sid,'linkone_snapshots')
        self.assertNotIn('body_locations',raw)
        self.assertEqual(raw['hash'],snap['hash'])
