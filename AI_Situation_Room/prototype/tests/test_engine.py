import tempfile
import unittest
from pathlib import Path
from prototype.store import Store
try:
    from prototype.engine import Engine
    from prototype.models import DemoModel
except ImportError:
    Engine = None
    DemoModel = None


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Engine, 'Agent execution is not implemented')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name)/'db.sqlite')
        self.sid = self.store.create_session('훈련 A')['id']
        self.other = self.store.create_session('훈련 B')['id']
        self.store.set_facts(self.sid, {'total':5,'rescued':4}, 0)
        self.engine = Engine(self.store, demo_model=DemoModel(delay=.02))
        self.addCleanup(self.engine.close)

    def test_parallel_reports_final_and_separate_memory(self):
        run = self.engine.submit(self.sid, '전체 상황과 대응을 정리해줘', 'analysis', '', 'one')
        self.engine.wait(run['id'])
        snap = self.store.snapshot(self.sid)
        specialists = [t for t in snap['tasks'] if t['role'] != 'critic']
        self.assertEqual(len(specialists), 3)
        self.assertLess(max(t['started_at'] for t in specialists), min(t['ended_at'] for t in specialists))
        critic = next(t for t in snap['tasks'] if t['role'] == 'critic')
        self.assertGreaterEqual(critic['started_at'], max(t['ended_at'] for t in specialists))
        self.assertEqual(snap['runs'][0]['status'], 'completed')
        self.assertIn('5', snap['messages'][-1]['content'])
        self.assertEqual(self.store.snapshot(self.other)['messages'], [])
        self.assertEqual(len(snap['runs'][0]['final']['report_ids']), 4)

    def test_simulation_advice_keeps_facts_and_assumptions(self):
        run = self.engine.submit(self.sid, '대안을 비교해줘', 'simulation', '자원 한 척 사용 불가', 'two')
        self.engine.wait(run['id'])
        snap = self.store.snapshot(self.sid)
        self.assertEqual(snap['session']['facts']['total'], 5)
        self.assertEqual(snap['session']['version'], 1)
        self.assertEqual(snap['runs'][0]['assumptions'], '자원 한 척 사용 불가')
        self.assertIn('가정', snap['messages'][-1]['content'])

    def test_duplicate_submission_does_not_execute_twice(self):
        r1 = self.engine.submit(self.sid, '전체 정리', 'analysis', '', 'same')
        r2 = self.engine.submit(self.sid, '전체 정리', 'analysis', '', 'same')
        self.engine.wait(r1['id'])
        self.assertEqual(r1['id'], r2['id'])
        self.assertEqual(len(self.store.snapshot(self.sid)['messages']), 2)

    def test_change_during_execution_marks_old_report(self):
        run = self.engine.submit(self.sid, '전체 정리', 'analysis', '', 'stale')
        import time
        for _ in range(100):
            if self.store.get_run(run['id'])['status'] == 'running': break
            time.sleep(.005)
        self.store.set_facts(self.sid, {'total':7,'rescued':4}, 1)
        self.engine.wait(run['id'])
        self.assertEqual(self.store.get_run(run['id'])['status'], 'stale')
        self.assertEqual(self.store.snapshot(self.sid)['session']['facts']['total'], 7)

    def test_provider_error_is_not_success_or_demo_fallback(self):
        class Broken:
            def respond(self, role, stage, context):
                raise RuntimeError('provider unavailable')
        self.engine.demo_model = Broken()
        run = self.engine.submit(self.sid, '검토', 'analysis', '', 'fail')
        self.engine.wait(run['id'])
        snap = self.store.snapshot(self.sid)
        self.assertEqual(snap['runs'][0]['status'], 'failed')
        self.assertEqual(len(snap['messages']), 1)

    def test_simple_information_request_only_assigns_information(self):
        r = self.engine.submit(self.sid, '명부만 확인해줘', 'analysis', '', 'select')
        self.engine.wait(r['id'])
        roles = [t['role'] for t in self.store.snapshot(self.sid)['tasks']]
        self.assertEqual(roles, ['intel','critic'])

    def test_commander_can_request_missing_information_without_assigning_agents(self):
        class QuestionOnly:
            def respond(self, role, stage, context):
                self.assert_role = role
                if stage == 'plan':
                    return {'summary':'판단에 필요한 현장 정보가 부족합니다.',
                            'questions':[{'question':'현재 사고 위치와 총원은 무엇인가요?',
                                          'reason':'대응 범위와 자원 배정을 결정하려면 필요합니다.',
                                          'priority':'high'}],
                            'update':{},'tasks':[]}, {}
                raise AssertionError('정보 요청만으로는 추가 모델 호출을 하지 않습니다.')
        self.engine.demo_model = QuestionOnly()
        run = self.engine.submit(self.sid, '현재 상황을 판단해줘', 'analysis', '', 'ask-user')
        self.engine.wait(run['id'])
        saved = self.store.get_run(run['id'])
        self.assertEqual(saved['status'], 'completed')
        self.assertEqual(saved['final']['information_requests'][0]['question'], '현재 사고 위치와 총원은 무엇인가요?')
        self.assertEqual(self.store.snapshot(self.sid)['tasks'], [])

    def test_specialist_information_request_is_forwarded_to_user(self):
        class SpecialistAsks:
            def respond(self, role, stage, context):
                if stage == 'plan':
                    return {'summary':'정보·대응 검토를 병렬로 진행합니다.', 'questions':[], 'update':{},
                            'tasks':[{'role':'intel','instruction':'현장 정보의 누락을 확인하세요.',
                                      'reason':'상황 판단에 필요한 정보 범위를 찾습니다.'}]}, {}
                if stage == 'report':
                    return {'summary':'현재 보고에서 위치 정보가 빠졌습니다.', 'findings':[],
                            'recommendation':'위치를 확인하세요.', 'uncertainties':[], 'evidence_ids':[],
                            'information_requests':[{'question':'현재 사고 위치를 알려주세요.',
                                                     'reason':'수색 범위와 자원 도착 판단에 필요합니다.',
                                                     'priority':'high'}]}, {}
                if role == 'critic':
                    return {'summary':'요원 요청을 확인했습니다.', 'findings':[], 'recommendation':'위치를 확인하세요.',
                            'uncertainties':[], 'evidence_ids':[], 'information_requests':[]}, {}
                return {'summary':'최종 판단', 'findings':[], 'recommendation':'위치를 확인하세요.',
                        'uncertainties':[], 'evidence_ids':[], 'information_requests':[]}, {}
        self.engine.demo_model = SpecialistAsks()
        run = self.engine.submit(self.sid, '현재 상황을 검토해줘', 'analysis', '', 'ask-specialist')
        self.engine.wait(run['id'])
        saved = self.store.get_run(run['id'])
        requests = saved['final']['information_requests']
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['source'], '정보요원')
        self.assertEqual(requests[0]['reason'], '수색 범위와 자원 도착 판단에 필요합니다.')
        self.assertTrue(any('추가 정보 요구' in event['label'] for event in self.store.snapshot(self.sid)['events']))

    def test_fire_report_creates_manual_dispatch_orders(self):
        run = self.engine.submit(self.sid, '묵호 동방 어선 화재. 검은 연기와 침수 우려가 있습니다.',
                                 'analysis', '', 'dispatch-manual')
        self.engine.wait(run['id'])
        saved = self.store.get_run(run['id'])
        orders = saved['decision']['dispatch_orders']
        asset_ids = {order['asset_id'] for order in orders}
        self.assertIn('coastal_rescue_mukho', asset_ids)
        self.assertIn('306함', asset_ids)
        self.assertIn('방제3호정', asset_ids)
        self.assertTrue(all(order['status'] == '제안·실제 출동 확인 필요' for order in orders))
        self.assertEqual({o['asset_id'] for o in saved['final']['dispatch_orders']}, asset_ids)

    def test_queued_followup_receives_previous_final_and_no_future_input(self):
        captured=[]
        class ObservedDemo(DemoModel):
            def respond(self,role,stage,context):
                if stage=='plan':captured.append((context['request']['prompt'],context['history']))
                return super().respond(role,stage,context)
        self.engine.demo_model=ObservedDemo(delay=.02)
        first=self.engine.submit(self.sid,'첫 요청','analysis','','first')
        second=self.engine.submit(self.sid,'그 판단의 근거는?','analysis','','second')
        self.engine.wait(first['id']);self.engine.wait(second['id'])
        self.assertEqual([m['role'] for m in captured[1][1]],['user','commander','user'])
        self.assertNotIn('그 판단의 근거는?',str(captured[0][1]))

    def test_one_session_backlog_does_not_block_other_session(self):
        import threading
        entered=threading.Event(); release=threading.Event(); other_done=threading.Event()
        class HeldDemo(DemoModel):
            def respond(model,role,stage,context):
                if stage=='plan' and context['request']['prompt']=='hold':
                    entered.set();release.wait(timeout=5)
                result=super().respond(role,stage,context)
                if stage=='final' and context['session']['id']==self.other:other_done.set()
                return result
        self.engine.demo_model=HeldDemo(delay=.001)
        try:
            self.engine.submit(self.sid,'hold','analysis','','hold')
            self.assertTrue(entered.wait(1))
            for i in range(3):self.engine.submit(self.sid,f'queued {i}','analysis','',f'q{i}')
            self.engine.submit(self.other,'독립 세션','analysis','','other')
            self.assertTrue(other_done.wait(1),'Same-session queue occupied every worker')
        finally:release.set()
