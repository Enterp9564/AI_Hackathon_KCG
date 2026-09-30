import http.client,json,tempfile,threading,unittest
from pathlib import Path
from prototype.store import Store
from prototype.engine import Engine
from prototype.models import DemoModel
from prototype.server import make_server

class SettingsHTTPTests(unittest.TestCase):
    def test_setting_and_current_cache_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');engine=Engine(store,demo_model=DemoModel(delay=0))
            server=make_server(store,engine,0,linkone_source=object())
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(method,path,data=None,token=None):
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
                headers={'Content-Type':'application/json'}
                if token:headers['X-Session-Token']=token
                conn.request(method,path,json.dumps(data) if data is not None else None,headers)
                response=conn.getresponse();status=response.status;body=json.loads(response.read());conn.close();return status,body
            try:
                _,config=request('GET','/api/config');token=config['token']
                self.assertTrue(config['critic']['enabled'])
                self.assertEqual(request('POST','/api/settings/critic',{'enabled':False})[0],403)
                self.assertEqual(request('POST','/api/settings/critic',{'enabled':'false'},token)[0],400)
                self.assertFalse(request('POST','/api/settings/critic',{'enabled':False},token)[1]['enabled'])
                sid=store.create_session('시험')['id']
                status,current=request('GET',f'/api/sessions/{sid}/linkone-current')
                self.assertEqual(status,200);self.assertEqual(current['status'],'unlinked')
                self.assertIsNone(server.current_situation.thread)
                self.assertEqual(request('GET','/api/sessions/missing/linkone-current')[0],404)
            finally:server.shutdown();server.server_close();engine.close()
