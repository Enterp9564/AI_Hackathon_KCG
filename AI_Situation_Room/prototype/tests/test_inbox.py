import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from prototype.store import Store, Conflict
from prototype.inbox import Inbox
from prototype.engine import Engine
from prototype.models import DemoModel


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'room.sqlite')
        self.inbox = Inbox(self.store)
        self.sid = self.store.create_session('A호', 'demo')['id']
        self.other = self.store.create_session('B호', 'demo')['id']
        self.inbox.link(self.sid, 'link-one', 'incident-a')
        self.payload = dict(report_id='r1', incident_id='incident-a', incident_title='A호 사고',
                            reported_at='2026-09-27T14:32:00+09:00', content='  구조 대상자 1명의 상태 변화\n')

    def tearDown(self):
        self.tmp.cleanup()

    def receive(self, **changes):
        return self.inbox.receive('link-one', dict(self.payload, **changes))

    def test_receipt_only_and_original_preserved(self):
        before = self.store.snapshot(self.sid)
        report = self.receive()
        self.assertEqual(before, {**self.store.snapshot(self.sid), 'server_time': before['server_time']})
        self.assertEqual(report['original'], self.payload)
        self.assertEqual(report['status'], 'pending')

    def test_reception_idempotency_and_conflict(self):
        first = self.receive()
        self.assertEqual(first['id'], self.receive()['id'])
        with self.assertRaises(Conflict): self.receive(content='다른 보고')
        self.assertEqual(len(self.inbox.list()['reports']), 1)

    def test_unknown_incident_and_source(self):
        with self.assertRaises(ValueError): self.receive(incident_id='unknown')
        with self.assertRaises(ValueError): self.inbox.receive('fake', self.payload)
        with self.assertRaises(Conflict): self.inbox.link(self.other, 'link-one', 'incident-a')

    def test_defer_reject_history(self):
        r = self.receive()
        self.inbox.act(self.sid, r['id'], 'later')
        self.assertEqual(self.inbox.get(r['id'])['status'], 'deferred')
        self.inbox.act(self.sid, r['id'], 'reject')
        self.assertEqual([h['action'] for h in self.inbox.get(r['id'])['history']], ['received','later','reject'])
        with self.assertRaises(Conflict): self.inbox.enqueue(self.sid, r['id'])
        self.assertEqual(self.store.snapshot(self.sid)['runs'], [])

    def test_wrong_session_and_concurrent_approval(self):
        r = self.receive()
        with self.assertRaises(Conflict): self.inbox.enqueue(self.other, r['id'])
        with ThreadPoolExecutor(4) as pool:
            runs = list(pool.map(lambda _: self.inbox.enqueue(self.sid, r['id']), range(8)))
        self.assertEqual(len({r['id'] for r in runs}), 1)
        snap = self.store.snapshot(self.sid)
        self.assertEqual(len(snap['runs']), 1)
        self.assertEqual(len(snap['messages']), 1)
        self.assertIn('[Link-One 수신 정보 인용]', snap['messages'][0]['content'])
        self.assertEqual(snap['messages'][0]['external_report_id'], r['id'])
        self.assertEqual(self.inbox.get(r['id'])['run_id'], runs[0]['id'])

    def test_queue_full_rolls_back_approval(self):
        for i in range(8): self.store.enqueue(self.sid, '대기 지시', 'analysis', '', str(i))
        r = self.receive()
        with self.assertRaises(Conflict): self.inbox.enqueue(self.sid, r['id'])
        self.assertEqual(self.inbox.get(r['id'])['status'], 'pending')

    def test_restart_retains_dedup_and_deleted_session_does_not_reroute(self):
        r = self.receive()
        self.inbox = Inbox(Store(self.store.path))
        self.assertEqual(self.receive()['id'], r['id'])
        self.store.delete_session(self.sid)
        self.inbox.link(self.other, 'link-one', 'incident-a')
        self.assertEqual(self.receive()['session_id'], self.sid)
        with self.assertRaises(Conflict): self.inbox.enqueue(self.other, r['id'])

    def test_quote_cannot_apply_facts_even_if_model_requests_update(self):
        class UpdatingModel(DemoModel):
            def respond(self, role, stage, context):
                result, meta = super().respond(role, stage, context)
                if stage == 'plan': result['update'] = {'total': 99}
                return result, meta
        r = self.receive()
        engine = Engine(self.store, demo_model=UpdatingModel(delay=.001))
        try:
            run = engine.submit(self.sid, None, 'analysis', '', None, inbox_report_id=r['id'])
            engine.wait(run['id'])
            self.assertEqual(self.store.get_run(run['id'])['status'], 'completed')
            self.assertEqual(self.store.snapshot(self.sid)['session']['facts'], {})
            with self.assertRaises(Conflict): self.store.apply_update(run['id'], {'total':99}, 0)
        finally: engine.close()

    def test_later_plan_does_not_treat_quote_as_user_fact(self):
        captured = []
        class CapturingModel(DemoModel):
            def respond(self, role, stage, context):
                if stage == 'plan': captured.append(context)
                return super().respond(role, stage, context)
        engine = Engine(self.store, demo_model=CapturingModel(delay=.001))
        try:
            r = self.receive()
            first = engine.submit(self.sid,None,'analysis','',None,inbox_report_id=r['id'])
            engine.wait(first['id'])
            second = engine.submit(self.sid,'추가 검토해줘','analysis','','followup')
            engine.wait(second['id'])
            self.assertTrue(any(m.get('external_report_id') for m in captured[0]['history']))
            self.assertFalse(any(m.get('external_report_id') for m in captured[1]['history']))
            self.assertFalse(any(e.get('external_report_id') for e in captured[1]['evidence']))
        finally: engine.close()

    def test_approval_and_reject_race_has_one_terminal_outcome(self):
        r = self.receive()
        def approve():
            try: return self.inbox.enqueue(self.sid,r['id'])
            except Conflict: return None
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(approve)
            b=pool.submit(self.inbox.act,self.sid,r['id'],'reject')
            a.result(); b.result()
        saved=self.inbox.get(r['id'])
        self.assertIn(saved['status'], ('sent','rejected'))
        self.assertEqual(len(self.store.snapshot(self.sid)['runs']), 1 if saved['status']=='sent' else 0)

    def test_live_agents_use_refreshed_facts(self):
        import json
        captured=[]
        class UpdatingLive(DemoModel):
            def respond(self, role, stage, context):
                result,meta=super().respond(role,stage,context)
                if stage=='plan': result['update']={'facts':{'total':2}}
                if stage=='report': captured.append(context)
                return result,meta
        sid=self.store.create_session('LIVE stub','live')['id']
        self.store.set_facts(sid,{'total':1},0)
        engine=Engine(self.store,live_model=UpdatingLive(delay=.001))
        try:
            run=engine.submit(sid,'총원 2명으로 정정 후 검토','analysis','','live-stub')
            engine.wait(run['id'])
            self.assertTrue(captured)
            for context in captured:
                self.assertEqual(context['session']['facts']['total'],2)
                facts=next(e for e in context['evidence'] if e['id']=='facts')
                self.assertEqual(json.loads(facts['content'])['total'],2)
        finally: engine.close()

    def test_external_provenance_survives_followup_summaries(self):
        captured=[]
        class RepeatingModel(DemoModel):
            def respond(self,role,stage,context):
                result,meta=super().respond(role,stage,context)
                if stage=='plan': captured.append(context)
                if stage=='final': result['summary']='외부 주장: 총원 99명'
                return result,meta
        engine=Engine(self.store,demo_model=RepeatingModel(delay=.001))
        try:
            report=self.receive(content='총원 99명이라는 미확인 주장')
            run=engine.submit(self.sid,None,'analysis','',None,inbox_report_id=report['id']);engine.wait(run['id'])
            for i in range(2):
                run=engine.submit(self.sid,'추가 검토','analysis','',f'followup-{i}');engine.wait(run['id'])
            self.assertFalse(any('99명' in m['content'] for m in captured[2]['history']))
            summaries=[m for m in self.store.snapshot(self.sid)['messages'] if m['role']=='commander']
            self.assertTrue(all(report['id'] in m.get('external_report_ids',[]) for m in summaries))
        finally: engine.close()
