import copy,json,unittest
from prototype.linkone_data import prepare,changes,evidence
from prototype.tests.test_linkone_sync import fixture,ROOM
from prototype.manuals import recommended_dispatch,manual_evidence

class ContextTests(unittest.TestCase):
 def snapshot(self):
  s=prepare(fixture(),ROOM);s.update(id='test',revision=1,diff=changes(None,s));return s
 def test_large_metadata_does_not_remove_patient_state(self):
  s=self.snapshot()
  for p in s['data']['person']:p['source']='x'*80000
  value=json.loads(evidence(s)['content'])
  self.assertEqual(len(value['people']),2)
  self.assertEqual(value['people'][0]['state']['severity'],'URGENT')
  self.assertFalse(value['comparison']['available'])
  self.assertNotIn('tables',value['diff'])
 def test_changed_snapshot_keeps_before_after_and_prioritizes_changed_patient(self):
  s=self.snapshot();new=copy.deepcopy(s);new['data']['person'][1]['name']='정정';new.update(revision=2,diff=changes(s,new))
  value=json.loads(evidence(new)['content'])
  self.assertTrue(value['comparison']['available'])
  self.assertEqual(value['diff']['tables']['person']['changed'][0]['fields']['name']['after'],'정정')
 def test_jeju_or_unknown_linkone_does_not_receive_donghae_candidates(self):
  for location in ('제주항 북방 1.5해리','미확인'):
   s={'linkone':{'room_id':ROOM},'facts':{'location':location}}
   self.assertEqual(recommended_dispatch('침수 대응',s),[])
   self.assertNotIn('donghae_assets',{e['id'] for e in manual_evidence(s)})
 def test_donghae_linkone_preserves_local_catalog(self):
  s={'linkone':{'room_id':ROOM},'facts':{'location':'묵호 동방 5해리'}}
  self.assertTrue(recommended_dispatch('침수 대응',s))

class IntegrationTests(unittest.TestCase):
 def test_scope_filters_every_role_and_final_questions_use_synthesis_only(self):
  import tempfile
  from pathlib import Path
  from prototype.store import Store
  from prototype.engine import Engine
  from prototype.models import DemoModel
  from prototype.linkone_sync import LinkOneSync
  from prototype.tests.test_linkone_sync import Source
  seen=[]
  class Model(DemoModel):
   def respond(self,role,stage,ctx):
    seen.append(ctx)
    result,meta=super().respond(role,stage,ctx)
    result['dispatch_orders']=[{'asset_id':'306함','order':'제주 출동','reason':'고정 목록'}]
    if stage=='final':result['information_requests']=[{'question':'최종 선택 질문','reason':'현재 상태 확인','priority':'high'}]
    elif stage!='plan':result['information_requests']=[{'question':'개별 요원의 추가 질문','reason':'검토 필요','priority':'medium'}]
    return result,meta
  with tempfile.TemporaryDirectory() as tmp:
   store=Store(Path(tmp)/'db');engine=Engine(store,demo_model=Model(.001));src=Source();src.payload['data']['room'][0]['waters']='제주항 북방'
   sync=LinkOneSync(store,engine,src)
   try:
    sid=sync.connect(ROOM)['id'];sync.wait(sid);engine.wait(sync.view(sid)['analysis_run_id']);snap=store.snapshot(sid)
    self.assertTrue(all(c['review_purpose']=='initial_baseline' for c in seen))
    self.assertTrue(all('donghae_assets' not in {e['id'] for e in c['evidence']} for c in seen))
    self.assertEqual(snap['runs'][0]['decision']['dispatch_orders'],[])
    self.assertTrue(all(t['report']['dispatch_orders']==[] for t in snap['tasks']))
    final=snap['runs'][0]['final'];self.assertEqual(final['dispatch_orders'],[])
    self.assertEqual([q['question'] for q in final['information_requests']],['최종 선택 질문'])
    self.assertTrue(any(t['report']['information_requests'] for t in snap['tasks']))
    self.assertIn('최초 수신',snap['runs'][0]['prompt'])
    seen.clear();r=sync.analyze(sid);engine.wait(r['id']);self.assertTrue(all(c['review_purpose']=='reanalysis' for c in seen))
   finally:sync.close();engine.close()
