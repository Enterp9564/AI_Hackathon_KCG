import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from prototype.store import Store, Conflict
from prototype.engine import Engine
from prototype.models import ModelError

class LocalTests(unittest.TestCase):
    def test_loopback_only_and_no_credentials(self):
        from prototype.local_llm import local_config
        self.assertEqual(local_config({'base_url':'http://localhost:1234','model':'qwen/test'})['base_url'],'http://127.0.0.1:1234/v1')
        for url in ['https://example.com/v1','http://127.0.0.1:1234@evil.com','http://127.0.0.1:1234/v1?key=a','http://192.168.0.1:1234','file:///tmp/x']:
            with self.subTest(url=url),self.assertRaises(ValueError):local_config({'base_url':url,'model':'m'})

    def test_adapter_preserves_rules_and_does_not_consume_reasoning(self):
        from prototype.local_llm import LocalModel
        calls=[]
        def request(url,payload=None,timeout=0):
            calls.append(payload)
            return {'choices':[{'finish_reason':'stop','message':{'content':'{"summary":"확인"}','reasoning_content':'private'}}],'model':'local-test'}
        with patch('prototype.local_llm.local_request',request):
            model=LocalModel({'base_url':'http://127.0.0.1:1234','model':'qwen/test'})
            result,meta=model.respond('sar','report',{'evidence':[{'id':'ship_tilt_guidance'}]})
        self.assertEqual(result,{'summary':'확인'})
        self.assertNotIn('private',json.dumps(meta))
        self.assertIn('실측 → 기준 → 대응상 의미',calls[0]['messages'][0]['content'])
        self.assertEqual(calls[0]['response_format']['type'],'json_schema')
        self.assertNotIn('Authorization',calls[0])
        for finish,content in [('length','{}'),('stop',''),('stop','[]'),('stop','not JSON')]:
            with patch('prototype.local_llm.local_request',return_value={'choices':[{'finish_reason':finish,'message':{'content':content,'reasoning_content':'{"summary":"wrong"}'}}]}),self.assertRaises(ModelError):
                model.respond('intel','report',{})

    def test_schema_limits_final_questions_and_evidence_to_supplied_ids(self):
        from prototype.local_llm import output_schema
        schema=output_schema('final',{'evidence':[{'id':'sar:provided'}]})
        self.assertEqual(schema['properties']['information_requests']['maxItems'],2)
        self.assertEqual(schema['properties']['evidence_ids']['items']['enum'],['sar:provided'])
        self.assertEqual(schema['properties']['evidence_links']['items']['properties']['evidence_ids']['items']['enum'],['sar:provided'])
        self.assertEqual(output_schema('report')['properties']['evidence_ids']['maxItems'],0)

    def test_settings_persist_busy_guard_and_failed_probe_keeps_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');engine=Engine(store)
            try:
                desired={'provider':'local','base_url':'http://127.0.0.1:1234','model':'qwen/test'}
                with patch('prototype.local_llm.probe',return_value={'ok':True}):
                    engine.configure_model(desired)
                self.assertEqual(engine.model_settings()['provider'],'local')
                self.assertTrue(engine.live_available())
                s=store.create_session('busy','live');r=store.enqueue(s['id'],'test','analysis','','busy')
                with self.assertRaises(Conflict):engine.configure_model({'provider':'openai'})
                store.update_run(r['id'],status='completed')
                with patch('prototype.local_llm.probe',side_effect=ValueError('unavailable')),self.assertRaises(ValueError):
                    engine.configure_model(dict(desired,model='absent'))
                self.assertEqual(engine.model_settings()['model'],'qwen/test')
                second=Engine(store)
                try:self.assertEqual(second.model_settings()['provider'],'local')
                finally:second.close()
            finally:engine.close()

    def test_local_final_uses_selected_questions_without_readding_agent_questions(self):
        from prototype.local_llm import LocalModel
        def answer(role,stage,context):
            question=lambda label:{'question':label,'reason':'가상 확인','priority':'high'}
            if stage=='plan':return {'summary':'배정','questions':[question('배정 질문')],'update':{},'dispatch_orders':[],'tasks':[{'role':'intel','instruction':'확인','reason':'시험'}]},{}
            return {'summary':'보고','findings':[],'recommendation':'확인','uncertainties':[],'evidence_ids':[],'dispatch_orders':[],'information_requests':[question('최종 질문' if stage=='final' else role+' 질문')]},{}
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');engine=Engine(store)
            try:
                with patch('prototype.local_llm.probe',return_value={'ok':True}):engine.configure_model({'provider':'local'})
                session=store.create_session('local','live')
                with patch.object(LocalModel,'respond',side_effect=answer):
                    r=engine.submit(session['id'],'가상 자료 분석','analysis','','selected');engine.wait(r['id'])
                run=store.get_run(r['id']);self.assertEqual([q['question'] for q in run['final']['information_requests']],['최종 질문'])
                self.assertTrue(store.snapshot(session['id'])['tasks'][0]['report']['information_requests'])
            finally:engine.close()

    def test_local_run_records_actual_provider_and_no_cloud_calls(self):
        from prototype.local_llm import LocalModel
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');engine=Engine(store)
            try:
                with patch('prototype.local_llm.probe',return_value={'ok':True}):engine.configure_model({'provider':'local','model':'qwen/test'})
                s=store.create_session('local','live')
                reply={'summary':'추가 정보 확인','questions':[{'question':'위치를 알려주세요','reason':'현장 위치 미기록','priority':'high'}],'tasks':[],'update':{},'dispatch_orders':[]}
                with patch.object(LocalModel,'respond',return_value=(reply,{'model':'qwen/test'})),patch.object(engine.live_model,'respond',side_effect=AssertionError('cloud called')):
                    r=engine.submit(s['id'],'가상 훈련 입력','analysis','','local-test');engine.wait(r['id'])
                snap=store.snapshot(s['id']);self.assertEqual(snap['runs'][0]['status'],'completed')
                self.assertEqual(snap['runs'][0]['model_config']['provider'],'local')
                self.assertEqual(snap['calls'][0]['requested_model'],'qwen/test')
                self.assertEqual(snap['calls'][0]['provider'],'local')
            finally:engine.close()

class LocalHTTPTests(unittest.TestCase):
    def test_settings_auth_probe_and_local_session(self):
        import urllib.request
        import urllib.error
        from prototype.server import make_server
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');engine=Engine(store);server=make_server(store,engine,0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                with urllib.request.urlopen(base+'/api/config') as r:token=json.load(r)['token']
                def post(path,data,auth=token):
                    req=urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Session-Token':auth})
                    try:
                        with urllib.request.urlopen(req) as r:return r.status,json.load(r)
                    except urllib.error.HTTPError as e:return e.code,json.load(e)
                cfg={'provider':'local','base_url':'http://127.0.0.1:1234','model':'qwen/test'}
                self.assertEqual(post('/api/settings/llm',cfg,'wrong')[0],403)
                with patch('prototype.local_llm.probe',return_value={'ok':True}):
                    self.assertEqual(post('/api/settings/llm/test',cfg)[0],200)
                    self.assertEqual(engine.model_settings()['provider'],'openai')
                    self.assertEqual(post('/api/settings/llm',cfg)[0],200)
                code,session=post('/api/sessions',{'title':'local test','mode':'live'})
                self.assertEqual(code,201)
                with urllib.request.urlopen(base+'/api/sessions/'+session['id']) as r:snap=json.load(r)
                self.assertEqual(snap['llm']['provider'],'local');self.assertEqual(snap['runs'],[])
                r=store.enqueue(session['id'],'hold','analysis','','hold')
                self.assertEqual(post('/api/settings/llm',{'provider':'openai'})[0],409)
            finally:server.shutdown();server.server_close();engine.close()
