import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from prototype.engine import Engine
from prototype.models import DemoModel
from prototype.store import Store
from prototype.tools import evidence_for
from prototype.manual_rag.context import with_manuals


class SessionContextLimitTests(unittest.TestCase):
    def test_large_context_reaches_model_and_completes(self):
        class Capture(DemoModel):
            received = False
            def respond(self, role, stage, context):
                if stage == 'plan':
                    self.received = any(len(e.get('content', '')) > 180000 for e in context['evidence'])
                return super().respond(role, stage, context)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'db')
            sid = store.create_session('긴 사건 훈련')['id']
            model = Capture(delay=0)
            engine = Engine(store, demo_model=model)
            def large_evidence(snap, prompt):
                return evidence_for(snap, prompt) + [{'id':'large-test', 'title':'시험 근거', 'content':'가' * 180001}]
            try:
                with patch('prototype.engine.evidence_for', large_evidence):
                    run = engine.submit(sid, '화재 전체 검토', 'analysis', '', 'large')
                    engine.wait(run['id'])
                self.assertTrue(model.received)
                self.assertEqual(store.get_run(run['id'])['status'], 'completed')
            finally:
                engine.close()

    def test_manual_merge_preserves_large_context(self):
        context = {'history':[{'content':'가' * 180001}], 'evidence':[]}
        item = {'id':'sar:test', 'content':'시험 근거'}
        result = with_manuals(context, {'status':'ok', 'items':[item]})
        self.assertEqual(result['history'], context['history'])
        self.assertEqual(result['evidence'], [item])
