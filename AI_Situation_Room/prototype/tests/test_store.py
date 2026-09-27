import tempfile
import unittest
from pathlib import Path
try:
    from prototype.store import Store, Conflict
except ImportError:
    Store = None
    Conflict = Exception


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Store, 'Session storage is not implemented')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.sqlite'
        self.store = Store(self.path)
        self.a = self.store.create_session('A', 'demo')['id']
        self.b = self.store.create_session('B', 'demo')['id']

    def test_facts_are_separate_and_survive_reopen(self):
        self.store.set_facts(self.a, {'total': 5, 'rescued': 4}, 0)
        snap = Store(self.path).snapshot(self.a)
        self.assertEqual(snap['session']['facts']['total'], 5)
        self.assertEqual(snap['session']['version'], 1)
        self.assertEqual(self.store.snapshot(self.b)['session']['facts'], {})

    def test_retries_create_one_run_and_message(self):
        a = self.store.enqueue(self.a, '상황 정리', 'analysis', '', 'request-1')
        b = self.store.enqueue(self.a, '상황 정리', 'analysis', '', 'request-1')
        self.assertEqual(a['id'], b['id'])
        self.assertEqual(len(self.store.snapshot(self.a)['messages']), 1)
        with self.assertRaises(Conflict):
            self.store.enqueue(self.a, '다른 내용', 'analysis', '', 'request-1')

    def test_version_conflict_and_invalid_counts_do_not_write(self):
        self.store.set_facts(self.a, {'total': 5, 'rescued': 4}, 0)
        with self.assertRaises(Conflict):
            self.store.set_facts(self.a, {'total': 7, 'rescued': 4}, 0)
        with self.assertRaises(ValueError):
            self.store.set_facts(self.a, {'total': 3, 'rescued': 4}, 1)
        self.assertEqual(self.store.snapshot(self.a)['session']['facts']['total'], 5)

    def test_attachment_and_run_cannot_cross_sessions(self):
        attachment = self.store.add_attachment(self.a, '명부.csv', 'id,rescued\nP01,true\nP02,false')
        self.assertEqual(attachment['summary']['total'], 2)
        self.assertEqual(self.store.snapshot(self.b)['attachments'], [])
        run = self.store.enqueue(self.a, '검토', 'analysis', '', 'req')
        with self.assertRaises(KeyError):
            self.store.get_run(run['id'], self.b)
        with self.assertRaises(ValueError):
            self.store.add_attachment(self.a, '명부.csv', 'id,rescued\nP01,true\nP01,false')

    def test_simulation_requires_assumptions_and_does_not_change_facts(self):
        self.store.set_facts(self.a, {'total': 5, 'rescued': 4}, 0)
        with self.assertRaises(ValueError):
            self.store.enqueue(self.a, '대안', 'simulation', '', 'empty')
        self.store.enqueue(self.a, '대안', 'simulation', '지원 자원 1개 사용 불가', 'sim')
        self.assertEqual(self.store.snapshot(self.a)['session']['facts']['total'], 5)

    def test_missing_session_rejected(self):
        with self.assertRaises(KeyError):
            self.store.snapshot('missing')
        with self.assertRaises(KeyError):
            self.store.enqueue('missing', 'hello', 'analysis', '', 'x')

    def test_delete_session_removes_records_and_pinned_setting(self):
        self.store.add_attachment(self.a, '메모.txt', '세션 전용 자료')
        self.store.enqueue(self.a, '검토', 'analysis', '', 'delete-me')
        self.store.finish_run(self.store.snapshot(self.a)['runs'][0]['id'], {'summary':'완료'})
        self.store.pin(self.a)
        self.assertEqual(self.store.delete_session(self.a), {'id':self.a, 'deleted':True})
        with self.assertRaises(KeyError):
            self.store.snapshot(self.a)
        self.assertIsNone(self.store.pinned())
        self.assertEqual(self.store.snapshot(self.b)['session']['title'], 'B')

    def test_delete_session_rejects_running_work(self):
        self.store.enqueue(self.a, '검토', 'analysis', '', 'active')
        with self.assertRaises(Conflict):
            self.store.delete_session(self.a)

    def test_location_change_clears_old_place_weather(self):
        self.store.set_facts(self.a, {'lat':37.5,'lon':129.5}, 0)
        self.store.set_weather(self.a, 1, {'valid_at':'2026-09-25T00:00','values':{'wind_speed_10m':4}})
        self.store.set_facts(self.a, {'lat':35.0,'lon':128.0}, 2)
        self.assertIsNone(self.store.snapshot(self.a)['session']['weather'])

    def test_restart_marks_unfinished_runs_interrupted(self):
        r=self.store.enqueue(self.a,'정리','analysis','','restart')
        reopened=Store(self.path)
        reopened.recover()
        self.assertEqual(reopened.get_run(r['id'])['status'],'interrupted')

    def test_completed_report_becomes_stale_after_later_correction(self):
        self.store.set_facts(self.a,{'total':5,'rescued':4},0)
        r=self.store.enqueue(self.a,'정리','analysis','','done')
        self.store.finish_run(r['id'],{'summary':'S1 보고'})
        self.store.set_facts(self.a,{'total':7,'rescued':4},1)
        snap=self.store.snapshot(self.a)
        self.assertEqual(snap['runs'][0]['status'],'stale')
        self.assertEqual(snap['messages'][-1]['status'],'stale')
