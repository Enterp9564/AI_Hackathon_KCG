import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from prototype.engine import Engine
from prototype.store import Store, Conflict
from prototype.server import make_server


class ManualSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db')
        self.service=SimpleNamespace(mode='hybrid',ready_vector=True)
        self.engine=Engine(self.store,manual_search=self.service);self.addCleanup(self.engine.close)

    def test_toggle_persists_and_preserves_service(self):
        self.assertTrue(self.engine.manual_settings()['enabled'])
        self.engine.configure_manual_search({'enabled':False})
        self.assertIsNone(self.engine.manual_search)
        second=Engine(self.store,manual_search=self.service)
        try:
            self.assertFalse(second.manual_settings()['enabled'])
            self.assertTrue(second.manual_settings()['available'])
            second.configure_manual_search({'enabled':True})
            self.assertIs(second.manual_search,self.service)
        finally:second.close()

    def test_invalid_unavailable_and_busy_do_not_change_state(self):
        for value in ['false',1,None]:
            with self.assertRaises(ValueError):self.engine.configure_manual_search({'enabled':value})
        sid=self.store.create_session('test')['id']
        self.store.enqueue(sid,'hold','analysis','','hold')
        with self.assertRaises(Conflict):self.engine.configure_manual_search({'enabled':False})
        self.assertIs(self.engine.manual_search,self.service)
        other=Engine(Store(Path(self.tmp.name)/'other'))
        try:
            with self.assertRaises(Conflict):other.configure_manual_search({'enabled':True})
            self.assertFalse(other.manual_settings()['enabled'])
        finally:other.close()

    def test_http_auth_config_and_persistence(self):
        server=make_server(self.store,self.engine,0,linkone_source=object())
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def get(path):
            with urllib.request.urlopen(base+path) as r:return json.load(r)
        def post(data,token):
            req=urllib.request.Request(base+'/api/settings/manual-search',data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Session-Token':token})
            try:
                with urllib.request.urlopen(req) as r:return r.status,json.load(r)
            except urllib.error.HTTPError as e:return e.code,json.load(e)
        try:
            cfg=get('/api/config');token=cfg['token']
            self.assertEqual(post({'enabled':False},'invalid')[0],403)
            self.assertEqual(post({'enabled':False},token)[0],200)
            self.assertFalse(get('/api/settings/manual-search')['enabled'])
            self.assertFalse(get('/api/config')['capabilities']['vector_search'])
            self.assertEqual(post({'enabled':True},token)[0],200)
            self.assertTrue(get('/api/config')['manual_search']['ready_vector'])
        finally:server.shutdown();server.server_close()
