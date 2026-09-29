import copy
import io
import json
import unittest
import urllib.error
import http.client
import tempfile
from pathlib import Path
from unittest.mock import patch
from prototype.models import ResponsesModel, ModelError


class CriticLoadTests(unittest.TestCase):
    def capture(self, role, context):
        sent=[]
        def transport(request, timeout):
            sent.append(json.loads(request.data))
            return io.BytesIO(json.dumps(dict(status='completed',output=[dict(type='message',
                content=[dict(type='output_text',text='{"summary":"점검"}')])])).encode())
        with patch('prototype.models.urllib.request.urlopen',transport):
            result, meta=ResponsesModel(key='test').respond(role,'report',context)
        return sent[0],meta

    def test_critic_has_short_prompt_budget_and_unchanged_model_effort(self):
        ordinary,_=self.capture('sar',{})
        critic,meta=self.capture('critic',{})
        self.assertLess(len(critic['instructions']),len(ordinary['instructions'])/2)
        self.assertEqual(critic['max_output_tokens'],2400)
        self.assertEqual(critic['reasoning'],ordinary['reasoning'])
        self.assertEqual(critic['model'],ordinary['model'])
        self.assertNotIn('plan 단계의 update',critic['instructions'])
        self.assertEqual(meta['diagnostics']['output_limit'],2400)

    def test_only_exact_duplicate_state_is_removed_and_evidence_is_preserved(self):
        facts={'notes':'화재 없음. 위치 미확인'}
        evidence=[dict(id='facts',content=json.dumps(facts)),
                  dict(id='sar:one',content='원문',limitations=['조건부'],original_sha256='hash')]
        context=dict(session=dict(facts=facts,incident={'fire':'종료'},version=2),evidence=evidence,
                     request=dict(kind='simulation',assumptions='화재 발생 가정'),reports=[{'report':{'summary':'보고'}}])
        before=copy.deepcopy(context)
        payload,_=self.capture('critic',context)
        reduced=json.loads(payload['input'])['context']
        self.assertNotIn('facts',reduced['session'])
        self.assertEqual(reduced['session_evidence_refs'],{'facts':'facts'})
        self.assertEqual(reduced['session']['incident'],context['session']['incident'])
        for key in ('evidence','request','reports'):self.assertEqual(reduced[key],context[key])
        self.assertEqual(context,before)

    def test_linkone_and_manual_safeguards_remain(self):
        payload,_=self.capture('critic',dict(session={'linkone':{'revision':1}},
            evidence=[{'id':'ship_tilt_guidance','content':'조건'}],manual_search={'status':'partial'}))
        for term in ('실측','미기록','출처','partial','가정','종결','resource_scope'):
            self.assertIn(term,payload['instructions'])

    def test_timeout_and_network_errors_have_safe_distinct_diagnostics(self):
        for error,kind in [(TimeoutError('secret-payload'),'timeout'),
                           (urllib.error.URLError(TimeoutError('secret')),'timeout'),
                           (urllib.error.URLError('private-host'),'network')]:
            with self.subTest(kind=kind),patch('prototype.models.urllib.request.urlopen',side_effect=error):
                with self.assertRaises(ModelError) as caught:ResponsesModel(key='test-secret').respond('critic','report',{})
                diagnostic=caught.exception.diagnostics
                self.assertEqual(diagnostic['error_kind'],kind)
                self.assertEqual(diagnostic['phase'],'await_headers')
                self.assertNotIn('secret',str(diagnostic))
                self.assertNotIn('private-host',str(diagnostic))

    def test_body_timeout_is_distinguished(self):
        class Body:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self):raise TimeoutError()
        with patch('prototype.models.urllib.request.urlopen',return_value=Body()):
            with self.assertRaises(ModelError) as caught:ResponsesModel(key='test').respond('critic','report',{})
        self.assertEqual(caught.exception.diagnostics['phase'],'read_body')

    def test_body_reset_and_truncated_response_keep_safe_diagnostics(self):
        for error in (ConnectionResetError('private-host'),http.client.IncompleteRead(b'private-data')):
            class Body:
                def __enter__(self):return self
                def __exit__(self,*a):pass
                def read(self):raise error
            with self.subTest(error=type(error).__name__),patch('prototype.models.urllib.request.urlopen',return_value=Body()):
                with self.assertRaises(ModelError) as caught:ResponsesModel(key='test').respond('critic','report',{})
                self.assertEqual(caught.exception.diagnostics['phase'],'read_body')
                self.assertEqual(caught.exception.diagnostics['error_kind'],'network')
                self.assertNotIn('private',str(caught.exception.diagnostics))

    def test_engine_persists_safe_failure_diagnostics(self):
        from prototype.engine import Engine
        from prototype.models import DemoModel
        from prototype.store import Store
        class FailCritic(DemoModel):
            def respond(self,role,stage,context):
                if role=='critic':raise ModelError('timeout',{'error_kind':'timeout','phase':'read_body'})
                return super().respond(role,stage,context)
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.sqlite');sid=store.create_session('test')['id']
            engine=Engine(store,demo_model=FailCritic(delay=0))
            try:
                run=engine.submit(sid,'화재 전체 검토','analysis','','test');engine.wait(run['id'])
                record=next(c for c in store.snapshot(sid)['calls'] if c['role']=='critic')
                self.assertEqual(record['status'],'failed')
                self.assertEqual(record['diagnostics']['error_kind'],'timeout')
            finally:engine.close()
