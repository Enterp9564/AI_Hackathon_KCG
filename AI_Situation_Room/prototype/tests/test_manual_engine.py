import copy
import tempfile
import unittest
from pathlib import Path
from prototype.engine import Engine
from prototype.models import DemoModel, ModelError
from prototype.store import Store
from prototype.inbox import Inbox
from prototype.manual_rag.retrieval import ManualSearch


class CaptureModel(DemoModel):
    def __init__(self):
        super().__init__(delay=0)
        self.inputs = []
    def respond(self, role, stage, context):
        self.inputs.append((role, stage, copy.deepcopy(context)))
        result, meta = super().respond(role, stage, context)
        sar = [e['id'] for e in context['evidence'] if e['id'].startswith('sar:')]
        if stage != 'plan' and sar: result['evidence_ids'] = sar
        return result, meta


class ManualEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name)/'test.sqlite')
        self.sid = self.store.create_session('A')['id']
        self.other = self.store.create_session('B')['id']
        self.model = CaptureModel()
        self.search = ManualSearch(mode='lexical'); self.addCleanup(self.search.close)
        self.engine = Engine(self.store, demo_model=self.model, manual_search=self.search)
        self.addCleanup(self.engine.close)

    def submit(self, prompt='화재와 실종자 수색 대응을 전체 검토해줘', request='one'):
        run = self.engine.submit(self.sid, prompt, 'analysis', '', request)
        self.engine.wait(run['id'])
        return self.store.get_run(run['id'])

    def test_role_evidence_reaches_critic_and_final(self):
        run = self.submit()
        self.assertEqual(run['status'], 'completed')
        specialists = [c for r,s,c in self.model.inputs if r in ('intel','sar','resource')]
        provided = {e['id'] for c in specialists for e in c['evidence'] if e['id'].startswith('sar:')}
        self.assertTrue(provided)
        for r,s,c in self.model.inputs:
            if r == 'critic' or s == 'final':
                self.assertLessEqual(provided, {e['id'] for e in c['evidence']})
        self.assertTrue(run['manual_context_ids'])

    def test_snapshots_scoped_and_detached_from_corpus(self):
        run = self.submit()
        context_id = run['manual_context_ids'][0]
        record = self.store.get_manual_context(self.sid, run['id'], context_id)
        before = copy.deepcopy(record)
        record['items'][0]['content'] = 'changed'
        self.assertEqual(before, self.store.get_manual_context(self.sid, run['id'], context_id))
        with self.assertRaises(KeyError): self.store.get_manual_context(self.other, run['id'], context_id)
        snap = self.store.snapshot(self.sid)
        self.assertTrue(snap['manual_contexts'])
        self.assertNotIn('items', snap['manual_contexts'][0])
        again = self.submit(request='one')
        self.assertEqual(run['manual_context_ids'], again['manual_context_ids'])

    def test_receive_only_does_not_search_or_change_facts(self):
        inbox = Inbox(self.store)
        inbox.link(self.sid,'link-one','incident-a')
        inbox.receive('link-one',dict(report_id='r1',incident_id='incident-a',incident_title='A',reported_at='2026-09-29T10:00:00+09:00',content='침수'))
        self.assertEqual(self.store.snapshot(self.sid)['manual_contexts'], [])
        self.assertEqual(self.model.inputs, [])

    def test_off_keeps_old_flow(self):
        self.engine.manual_search = None
        run = self.submit()
        self.assertEqual(run['status'], 'completed')
        self.assertEqual(self.store.snapshot(self.sid)['manual_contexts'], [])
        self.assertFalse(any(e['id'].startswith('sar:') for _,_,c in self.model.inputs for e in c['evidence']))

    def test_search_failure_is_visible_and_not_fabricated_evidence(self):
        def broken(*a, **k): raise RuntimeError('private diagnostic')
        self.search.retrieve = broken
        run = self.submit()
        self.assertEqual(run['status'], 'completed')
        self.assertEqual(run['manual_search']['status'], 'error')
        self.assertIn('매뉴얼', run['manual_search']['reason'])
        self.assertNotIn('private diagnostic', str(run))

    def test_unknown_evidence_link_is_rejected(self):
        result = dict(summary='s', findings=[], recommendation='r', uncertainties=[], evidence_ids=[],
                      evidence_links=[dict(claim='r',evidence_ids=['missing'],application='a',limitations=[])])
        with self.assertRaises(ModelError): self.engine.validate(result,'report',{'evidence':[]})


if __name__ == '__main__': unittest.main()
