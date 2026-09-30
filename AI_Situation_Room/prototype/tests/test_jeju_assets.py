import json
import unittest
from prototype.manuals import manual_evidence,normalize_orders,recommended_dispatch


class JejuAssetsTests(unittest.TestCase):
    def test_jeju_case_receives_registered_ships_and_source(self):
        for location in ['제주항 북방 1.5해리','서귀포 남방 5해리']:
            session={'linkone':{'room_id':'test'},'facts':{'location':location}}
            evidence={e['id']:e for e in manual_evidence(session)}
            self.assertIn('jeju_assets',evidence)
            self.assertNotIn('donghae_assets',evidence)
            catalog=json.loads(evidence['jeju_assets']['content'])
            self.assertEqual({u['name'] for u in catalog['units']},{'1505함','3012함','P-36'})
            self.assertTrue(all(u['affiliation']=='제주해양경찰서' for u in catalog['units']))
            self.assertIn('Link-One',catalog['source'])
            self.assertEqual(recommended_dispatch('침수',session),[])

    def test_orders_keep_jeju_candidates_and_filter_wrong_region(self):
        orders=[{'asset_id':id,'order':'구조 지원 검토','reason':'현장 확인 후 판단'} for id in ['jeju_1505','306함']]
        session={'linkone':{},'facts':{'location':'제주항'}}
        result=normalize_orders(orders,session)
        self.assertEqual([r['asset_id'] for r in result],['jeju_1505'])
        self.assertEqual(result[0]['asset_name'],'1505함')
        self.assertEqual(result[0]['basis'],['basic_manual','jeju_assets'])
        self.assertIn('확인 필요',result[0]['status'])

    def test_other_regions_do_not_receive_jeju_or_wrong_fallback(self):
        for location in ['미확인','부산항','제주 또는 동해항 미확정']:
            session={'linkone':{'room_id':'test'},'facts':{'location':location}}
            evidence={e['id'] for e in manual_evidence(session)}
            self.assertFalse({'jeju_assets','donghae_assets'} & evidence)
        donghae={'facts':{'location':'묵호 동방'}}
        self.assertNotIn('jeju_assets',{e['id'] for e in manual_evidence(donghae)})
        self.assertTrue(recommended_dispatch('침수',donghae))

    def test_manual_library_exposes_both_catalogs(self):
        self.assertTrue({'donghae_assets','jeju_assets'}<={e['id'] for e in manual_evidence()})

    def test_engine_preserves_jeju_orders_in_every_role_and_synthesis(self):
        import tempfile
        from pathlib import Path
        from prototype.engine import Engine
        from prototype.models import DemoModel
        from prototype.store import Store
        seen=[]
        class Model(DemoModel):
            def respond(self,role,stage,context):
                seen.append({e['id'] for e in context['evidence']})
                result,metadata=super().respond(role,stage,context)
                result['dispatch_orders']=[{'asset_id':id,'order':'위치 확인 후 구조 지원 검토','reason':'제주 사고 대응'}
                                          for id in ['jeju_3012','306함']]
                return result,metadata
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.sqlite');s=store.create_session('제주 세력 시험')
            store.set_facts(s['id'],{'location':'제주항 북방'},s['version'])
            engine=Engine(store,demo_model=Model(0))
            try:
                run=engine.submit(s['id'],'침수 전체 분석','analysis','','jeju-test');engine.wait(run['id'])
                snapshot=store.snapshot(s['id']);run=store.get_run(run['id'])
                self.assertEqual(run['status'],'completed')
                self.assertTrue(all('jeju_assets' in ids and 'donghae_assets' not in ids for ids in seen))
                reports=[run['decision'],run['final'],*[t['report'] for t in snapshot['tasks']]]
                self.assertTrue(all([o['asset_id'] for o in r['dispatch_orders']]==['jeju_3012'] for r in reports))
                self.assertEqual(snapshot['resource_scope']['catalog_ids'],['jeju_assets'])
            finally:engine.close()
