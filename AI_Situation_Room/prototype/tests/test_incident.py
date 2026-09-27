import tempfile
import unittest
from pathlib import Path
from prototype.store import Store, Conflict

class IncidentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db')
        self.sid=self.store.create_session('A')['id']
    def run_for(self, prompt='사용자 신고', kind='analysis'):
        import uuid
        return self.store.enqueue(self.sid,prompt,kind,'가정' if kind=='simulation' else '',str(uuid.uuid4()))
    def apply(self, patch):
        r=self.run_for()
        return self.store.apply_update(r['id'],patch,self.store.snapshot(self.sid)['session']['version'])
    def test_patch_preserves_name_identity_and_other_attributes_and_audit(self):
        self.apply({'facts':{'total':8,'rescued':6,'remaining':2},'roster':{'engineer':{'name':'이기란','role':'기관장','location':'청해호','condition':'의식 명료·부상 보고 없음'}}})
        before=self.store.snapshot(self.sid)['session']['incident']['roster']['engineer']
        self.apply({'roster':{'engineer':{'name':'이기관'}}})
        s=self.store.snapshot(self.sid)
        self.assertEqual(s['session']['incident']['roster']['engineer'],{**before,'name':'이기관'})
        self.assertEqual(s['events'][-1]['before']['incident']['roster']['engineer']['name'],'이기란')
        self.assertEqual(s['events'][-1]['source_id'],s['messages'][-1]['id'])
    def test_transfer_does_not_inflate_rescued_and_persists(self):
        self.apply({'facts':{'total':8,'rescued':8,'remaining':0},'distribution':{'동진호':3,'구조정':3,'301함':2}})
        self.apply({'distribution':{'동진호':0,'구조정':0,'301함':5,'묵호항':3}})
        s=Store(self.store.path).snapshot(self.sid)['session']
        self.assertEqual(s['facts']['rescued'],8)
        self.assertEqual(sum(s['incident']['distribution'].values()),8)
    def test_invalid_sum_rejects_whole_transaction(self):
        self.apply({'facts':{'total':8},'distribution':{'청해호':8}})
        before=self.store.snapshot(self.sid)['session']
        with self.assertRaises(ValueError):self.apply({'facts':{'total':9},'distribution':{'청해호':10}})
        self.assertEqual(self.store.snapshot(self.sid)['session'],before)
    def test_simulation_cannot_mutate(self):
        r=self.run_for(kind='simulation')
        with self.assertRaises(ValueError):self.store.apply_update(r['id'],{'facts':{'total':9}},0)
        self.assertEqual(self.store.snapshot(self.sid)['session']['facts'],{})
    def test_idempotency_version_and_separate_session(self):
        r=self.run_for();patch={'facts':{'total':8}}
        self.store.apply_update(r['id'],patch,0)
        self.store.apply_update(r['id'],patch,0)
        self.assertEqual(self.store.snapshot(self.sid)['session']['version'],1)
        r2=self.run_for()
        with self.assertRaises(Conflict):self.store.apply_update(r2['id'],patch,0)
        other=self.store.create_session('B')['id']
        self.assertEqual(self.store.snapshot(other)['session']['facts'],{})
    def test_unknown_fields_and_wrong_types_rejected(self):
        for patch in [{'roster':{'x':{'name':3}}},{'distribution':{'a':True}},{'facts':{'total':-1}},{'private_key':'x'}]:
            with self.subTest(patch=patch),self.assertRaises(ValueError):self.apply(patch)

class IntakeFlowTests(unittest.TestCase):
    def test_intake_persists_before_analysis_and_simple_update_skips_specialists(self):
        from prototype.engine import Engine
        class Provider:
            def respond(self,role,stage,context):
                assert stage=='plan', 'Simple updates must not invoke specialists or final model'
                return {'summary':'총원을 8명으로 반영했습니다.','update':{'facts':{'total':8}},'tasks':[]},{}
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'db');sid=store.create_session('입력')['id']
            engine=Engine(store,demo_model=Provider())
            try:
                run=engine.submit(sid,'총 8명입니다.','analysis','','first');engine.wait(run['id'])
                snap=store.snapshot(sid)
                self.assertEqual(snap['session']['facts'],{'total':8})
                self.assertEqual(snap['runs'][0]['status'],'completed')
                self.assertEqual(snap['tasks'],[])
                self.assertEqual(len(snap['calls']),1)
                self.assertIn(snap['messages'][0]['id'],snap['runs'][0]['final']['evidence_ids'])
            finally:engine.close()
    def test_original_reports_are_citable_and_simulation_not_evidence_fact(self):
        from prototype.tools import evidence_for
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'db');sid=store.create_session('입력')['id']
            store.enqueue(sid,'총 8명 신고','analysis','','a')
            store.enqueue(sid,'만약 10명이면','simulation','10명 가정','b')
            s=store.snapshot(sid);e=evidence_for(s,'검토')
            self.assertIn(s['messages'][0]['id'],[x['id'] for x in e])
            self.assertNotIn(s['messages'][1]['id'],[x['id'] for x in e])

    def test_basic_manual_and_force_catalog_are_always_available_as_evidence(self):
        from prototype.tools import evidence_for
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'db');sid=store.create_session('입력')['id']
            evidence=evidence_for(store.snapshot(sid),'화재 출동')
            ids={item['id'] for item in evidence}
            self.assertIn('basic_manual',ids)
            self.assertIn('donghae_assets',ids)
            catalog=next(item for item in evidence if item['id']=='donghae_assets')['content']
            self.assertIn('3007함',catalog)

class ManualIncidentTests(unittest.TestCase):
    setUp=IncidentTests.setUp
    apply=IncidentTests.apply
    run_for=IncidentTests.run_for
    def test_manual_note_edit_preserves_remaining_and_rejects_bad_total(self):
        self.apply({'facts':{'total':8,'rescued':6,'remaining':2},'distribution':{'청해호':2,'동진호':3,'구조정':3}})
        self.store.set_facts(self.sid,{'total':8,'rescued':6,'notes':'추가 메모'},1)
        self.assertEqual(self.store.snapshot(self.sid)['session']['facts']['remaining'],2)
        with self.assertRaises(ValueError):self.store.set_facts(self.sid,{'total':9,'rescued':6},2)

    def test_receipt_never_cites_missing_facts(self):
        from prototype.incident import receipt
        r=receipt({'facts':{},'incident':{'vessel':'A'},'version':1},'source','저장')
        self.assertNotIn('facts',r['evidence_ids'])
        self.assertIn('incident',r['evidence_ids'])

    def test_explicit_leading_report_time_is_saved_without_model_guess(self):
        r=self.run_for('14:12 지원선 현장 도착')
        self.store.apply_update(r['id'],{'conditions':{'fire':'연기 지속'}},0)
        self.assertEqual(self.store.snapshot(self.sid)['session']['incident']['report_time'],'14:12')

    def test_name_correction_updates_derived_notes_but_keeps_original_message(self):
        self.apply({'facts':{'notes':'기관장 이기란 잔류'},'roster':{'e':{'name':'이기란','role':'기관장'}}})
        self.apply({'roster':{'e':{'name':'이기관'}}})
        s=self.store.snapshot(self.sid)
        self.assertEqual(s['session']['facts']['notes'],'기관장 이기관 잔류')
        self.assertIn('이기란',s['events'][-1]['before']['facts']['notes'])

    def test_final_report_keeps_full_original_timeline(self):
        from prototype.engine import Engine
        from prototype.models import DemoModel
        engine=Engine(self.store,demo_model=DemoModel(delay=.001))
        try:
            for n,msg in enumerate(['14:12 첫 이송 3명','14:50 지원 종료 정리해줘']):
                r=engine.submit(self.sid,msg,'analysis','',str(n));engine.wait(r['id'])
            report=self.store.get_run(r['id'])['final']
            self.assertEqual([x['text'] for x in report['timeline']],['14:12 첫 이송 3명','14:50 지원 종료 정리해줘'])
        finally:engine.close()

    def test_distribution_is_complete_snapshot_not_additive_places(self):
        self.apply({'facts':{'total':8,'rescued':3,'remaining':5},'distribution':{'청해호 선수':5,'동진호':3}})
        self.apply({'facts':{'rescued':6,'remaining':2},'distribution':{'청해호':2,'동진호':3,'구조정':3}})
        self.assertEqual(self.store.snapshot(self.sid)['session']['incident']['distribution'],{'청해호':2,'동진호':3,'구조정':3})
