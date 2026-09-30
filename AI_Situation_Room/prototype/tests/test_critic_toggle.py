import tempfile
import unittest
from pathlib import Path
from prototype.store import Store
from prototype.engine import Engine
from prototype.models import DemoModel
from prototype.patient_alerts import INTERVAL

class CriticToggleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db.sqlite'
        self.store=Store(self.path);self.sid=self.store.create_session('훈련')['id']
    def tearDown(self):self.tmp.cleanup()
    def settings(self,on):
        self.assertTrue(hasattr(self.store,'set_critic_enabled'),'critic setting API missing')
        return self.store.set_critic_enabled(on)
    def test_alert_interval_is_two(self):self.assertEqual(INTERVAL,2)
    def test_default_persistence_and_strict_boolean(self):
        self.assertTrue(hasattr(self.store,'critic_settings'))
        self.assertTrue(self.store.critic_settings()['enabled'])
        self.settings(False);self.assertFalse(Store(self.path).critic_settings()['enabled'])
        for value in ('false',0,None,[],{}):
            with self.assertRaises(ValueError):self.settings(value)
    def test_queue_and_duplicate_keep_policy(self):
        a=self.store.enqueue(self.sid,'화재 전체 검토','analysis','','a')
        self.settings(False)
        b=self.store.enqueue(self.sid,'화재 전체 검토','analysis','','b')
        again=self.store.enqueue(self.sid,'화재 전체 검토','analysis','','a')
        self.assertTrue(a['critic_enabled']);self.assertTrue(again['critic_enabled'])
        self.assertFalse(b['critic_enabled']);self.assertEqual(a['id'],again['id'])
    def test_off_skips_critic_but_final_and_validation_remain(self):
        self.settings(False)
        class Capture(DemoModel):
            def __init__(self):super().__init__(delay=0);self.contexts=[]
            def respond(self,role,stage,context):
                self.contexts.append((role,stage,context));return super().respond(role,stage,context)
        model=Capture();engine=Engine(self.store,demo_model=model)
        try:
            r=engine.submit(self.sid,'화재 전체 검토','analysis','','off');engine.wait(r['id'])
            snap=self.store.snapshot(self.sid);run=self.store.get_run(r['id'])
            self.assertEqual(run['status'],'completed');self.assertEqual(run['critic_review']['status'],'skipped')
            self.assertFalse(any(t['role']=='critic' for t in snap['tasks']))
            self.assertFalse(any(c['role']=='critic' for c in snap['calls']))
            finals=[c for r,s,c in model.contexts if r=='commander' and s=='final']
            self.assertEqual(len(finals),1);self.assertFalse(finals[0]['review_policy']['critic_enabled'])
            self.assertTrue(finals[0]['reports'])
        finally:engine.close()
    def test_on_and_direct_receipt(self):
        engine=Engine(self.store,demo_model=DemoModel(delay=0))
        try:
            r=engine.submit(self.sid,'화재 전체 검토','analysis','','on');engine.wait(r['id'])
            self.assertEqual(self.store.get_run(r['id']).get('critic_review',{}).get('status'),'completed')
        finally:engine.close()

class CriticPolicyExecutionTests(unittest.TestCase):
    def test_queued_policies_and_invalid_evidence(self):
        import threading
        from prototype.models import ModelError
        started=threading.Event();release=threading.Event()
        class BlockFirst(DemoModel):
            def respond(self,role,stage,context):
                if stage=='plan' and context['request']['request_id']=='one':
                    started.set();release.wait(4)
                return super().respond(role,stage,context)
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');sid=store.create_session('시험')['id'];engine=Engine(store,demo_model=BlockFirst(delay=0))
            try:
                a=engine.submit(sid,'화재 전체 검토','analysis','','one');self.assertTrue(started.wait(2))
                b=engine.submit(sid,'화재 전체 검토','analysis','','two');engine.configure_critic({'enabled':False})
                c=engine.submit(sid,'화재 전체 검토','analysis','','three');release.set()
                for r in (a,b,c):engine.wait(r['id'])
                self.assertEqual([store.get_run(r['id'])['critic_review']['status'] for r in (a,b,c)],['completed','completed','skipped'])
                with self.assertRaises(ModelError):
                    engine.validate({'summary':'x','recommendation':'x','findings':[],'uncertainties':[],'evidence_ids':['invented']},'final',{'evidence':[]})
            finally:release.set();engine.close()
    def test_direct_receipt_and_critic_failure(self):
        from prototype.models import ModelError
        class Direct(DemoModel):
            def respond(self,role,stage,context):
                result,meta=super().respond(role,stage,context)
                if stage=='plan':result.update(tasks=[],update={'facts':{'total':2}})
                return result,meta
        class FailCritic(DemoModel):
            def respond(self,role,stage,context):
                if role=='critic':raise ModelError('fixture critic failure')
                return super().respond(role,stage,context)
        for model,expected in ((Direct(delay=0),'not_applicable'),(FailCritic(delay=0),'failed')):
            with tempfile.TemporaryDirectory() as tmp:
                store=Store(Path(tmp)/'db');sid=store.create_session('시험')['id'];engine=Engine(store,demo_model=model)
                try:
                    r=engine.submit(sid,'화재 전체 검토','analysis','','test');engine.wait(r['id'])
                    self.assertEqual(store.get_run(r['id'])['critic_review']['status'],expected)
                finally:engine.close()
