from prototype.tests import test_http
from prototype.manual_rag.retrieval import ManualSearch
import shutil
import urllib.request
from pathlib import Path


class ManualHTTPTests(test_http.HTTPTests):
    def setUp(self):
        super().setUp()
        self.search=ManualSearch(mode='lexical')
        self.addCleanup(self.search.close)
        self.engine.manual_search=self.search

    def test_context_get_is_scoped_and_read_only(self):
        _, a=self.request('/api/sessions',{'title':'A','mode':'demo'})
        _, b=self.request('/api/sessions',{'title':'B','mode':'demo'})
        _, run=self.request('/api/sessions/'+a['id']+'/message',dict(prompt='화재와 수색을 전체 검토',request_id='one'))
        self.engine.wait(run['id'])
        run=self.store.get_run(run['id'])
        cid=run['manual_context_ids'][0]
        path=f"/api/sessions/{a['id']}/runs/{run['id']}/manual-contexts/{cid}"
        code, result=self.request(path)
        self.assertEqual(code,200)
        self.assertTrue(result['items'])
        self.assertEqual(self.request(path.replace(a['id'],b['id']))[0],404)
        self.assertEqual(self.request(path.replace(run['id'],'missing'))[0],404)
        self.assertEqual(len(self.store.snapshot(a['id'])['runs']),1)

    def test_raw_files_not_exposed_and_config_reports_actual_mode(self):
        for path in ('/api/manual-sources/../../.env/pdf','/api/manual-sources/unknown/pdf'):
            self.assertEqual(self.request(path)[0],404)
        _,config=self.request('/api/config')
        self.assertEqual(config['manual_search']['mode'],'lexical')
        self.assertFalse(config['capabilities']['vector_search'])

    def test_pdf_refuses_changed_bytes_and_different_expected_version(self):
        root = Path(self.tmp.name)/'corpus'
        shutil.copytree(self.search.corpus.root, root)
        self.search.corpus.root = root
        source = next(iter(self.search.corpus.sources.values()))
        path = '/api/manual-sources/'+source['source_id']+'/pdf'
        expected = source['original_sha256']
        with urllib.request.urlopen(self.base+path+'?sha256='+expected) as response:
            self.assertEqual(response.read()[:4], b'%PDF')
        for suffix in ('', '?sha256='+'0'*64):
            self.assertEqual(self.request(path+suffix)[0], 409)
        (root/source['original_path']).write_bytes(b'%PDF-revised')
        self.assertEqual(self.request(path+'?sha256='+expected)[0], 409)
        # Simulate a legitimate registry reload to a newer edition.
        from prototype.manual_rag.corpus import digest
        source['original_sha256'] = digest(b'%PDF-revised')
        self.assertEqual(self.request(path+'?sha256='+expected)[0], 409)
