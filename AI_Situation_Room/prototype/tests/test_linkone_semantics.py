import tempfile
import unittest
from pathlib import Path
from prototype.store import Store
from prototype.engine import Engine
from prototype.models import DemoModel
from prototype.linkone_sync import LinkOneSync
from prototype.tests.test_linkone_sync import Source
from prototype.tools import evidence_for

class SemanticsTests(unittest.TestCase):
    def test_reference_reaches_every_analysis_stage_but_not_unrelated_sessions(self):
        seen=[]
        class RecordingModel(DemoModel):
            def respond(self,role,stage,context):
                seen.append((role,stage,{e['id']:e for e in context['evidence']}))
                return super().respond(role,stage,context)
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');engine=Engine(store,demo_model=RecordingModel(.001));sync=LinkOneSync(store,engine,Source())
            try:
                from prototype.tests.test_linkone_sync import ROOM
                sid=sync.connect(ROOM)['id'];sync.wait(sid);engine.wait(sync.view(sid)['analysis_run_id'])
                self.assertEqual({x[0] for x in seen},{'commander','intel','sar','resource','critic'})
                for role,stage,items in seen:
                    self.assertIn('linkone_semantics',items,(role,stage))
                    self.assertIn('ship_tilt_guidance',items,(role,stage))
                    for word in ('7.5°','승선원의 생존확률이 아니다','미설정'):
                        self.assertIn(word,items['ship_tilt_guidance']['content'])
                    for word in ('RESCUED_ON_SHIP','ACK','UNDO','roll','미분류','REOPEN'):
                        self.assertIn(word,items['linkone_semantics']['content'])
                ordinary=store.create_session('일반')
                self.assertNotIn('linkone_semantics',{e['id'] for e in evidence_for(store.snapshot(ordinary['id']),'검토')})
                self.assertNotIn('ship_tilt_guidance',{e['id'] for e in evidence_for(store.snapshot(ordinary['id']),'검토')})
            finally:sync.close();engine.close()
