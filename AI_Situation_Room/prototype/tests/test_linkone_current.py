import copy,importlib.util,tempfile,unittest
from pathlib import Path
from prototype.store import Store
from prototype.tests.test_linkone_sync import fixture,ROOM,OTHER,P1,P2

class CurrentTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('prototype.linkone_current'),'current state module missing')
        from prototype import linkone_current
        return linkone_current
    def test_summary_records_and_fingerprint(self):
        m=self.module();raw=fixture()['data']
        raw['person_event'].append(dict(id='9007199254740993',room_id=ROOM,person_id=P1,type='RECORD',payload={'text':'음성 기록','via':'VOICE'},server_at='2026-09-30T00:00:00Z'))
        a=m.normalize_current(m.project_snapshot(raw,ROOM),ROOM)
        self.assertEqual(a['summary']['rescued'],1);self.assertEqual(a['summary']['unrecorded'],1)
        self.assertEqual(a['recent_records'][0]['id'],'9007199254740993')
        raw['person_event'][-1]['payload']['text']='정정'
        b=m.normalize_current(m.project_snapshot(raw,ROOM),ROOM)
        self.assertNotEqual(a['fingerprint'],b['fingerprint'])
        raw['person'][1]['not_boarded_at']='now'
        self.assertEqual(m.normalize_current(m.project_snapshot(raw,ROOM),ROOM)['summary']['total'],1)
    def test_cache_no_ai_and_restart_error_history(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');s=store.create_session('훈련')
            with store.db() as db:s['linkone']={'room_id':ROOM};store._put_session(db,s)
            payload=m.project_snapshot(fixture()['data'],ROOM)
            class Source:
                error=False
                def poll(self,rooms,known):
                    if self.error:raise RuntimeError('private error')
                    data=m.normalize_current(payload,ROOM)
                    return {ROOM:dict(fingerprint=data['fingerprint'],data=payload if known.get(ROOM)!=data['fingerprint'] else None)}
                def close(self):pass
            source=Source();c=m.CurrentSituation(store,source,start=False)
            before=store.snapshot(s['id'])['session']
            self.assertEqual(c.tick(),3);c.tick()
            self.assertEqual(c.view(s['id'])['summary']['rescued'],1)
            snap=store.snapshot(s['id']);self.assertEqual(snap['session'],before);self.assertFalse(snap['runs']);self.assertFalse(snap['messages'])
            with store.db() as db:self.assertEqual(len(store._items(db,s['id'],'linkone_current_snapshots')),1)
            source.error=True;self.assertEqual(c.tick(),6)
            self.assertEqual(c.view(s['id'])['summary']['rescued'],1)
            self.assertNotIn('private',str(c.view(s['id'])))
            restarted=m.CurrentSituation(store,source,start=False)
            self.assertEqual(restarted.view(s['id'])['status'],'waiting')
            self.assertEqual(restarted.view(s['id'])['summary']['rescued'],1)
            c.close();restarted.close()
    def test_reject_cross_room_and_cancellation(self):
        m=self.module();raw=fixture()['data'];raw['person_event']=[dict(id='7',room_id=ROOM,person_id=P1,type='RECORD',payload={'text':'과거'}),dict(id='8',room_id=ROOM,person_id=P1,type='UNDO',undo_of='7',payload={})]
        p=m.project_snapshot(raw,ROOM);n=m.normalize_current(p,ROOM)
        self.assertTrue(n['recent_records'][0]['canceled'])
        p['person'][0]['room_id']=OTHER
        with self.assertRaises(ValueError):m.normalize_current(p,ROOM)

class CurrentEdgeTests(unittest.TestCase):
    def test_inflight_reconnect_and_deleted_session_are_ignored(self):
        from prototype.linkone_current import CurrentSituation,normalize_current,project_snapshot
        for remove in (False,True):
            with self.subTest(remove=remove),tempfile.TemporaryDirectory() as tmp:
                store=Store(Path(tmp)/'db');s=store.create_session('시험')
                with store.db() as db:s['linkone']={'room_id':ROOM};store._put_session(db,s)
                class Source:
                    def poll(self,rooms,known):
                        if remove:store.delete_session(s['id'])
                        else:
                            with store.db() as db:s['linkone']['room_id']=OTHER;store._put_session(db,s)
                        p=project_snapshot(fixture()['data'],ROOM)
                        return {ROOM:dict(fingerprint=normalize_current(p,ROOM)['fingerprint'],data=p)}
                    def close(self):pass
                current=CurrentSituation(store,Source(),start=False)
                try:
                    current.tick()
                    with store.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM linkone_current_cache').fetchone()[0],0)
                    if not remove:self.assertIsNone(current.view(s['id'])['summary'])
                finally:current.close()
    def test_limits_partial_unknown_and_order(self):
        from prototype.linkone_current import normalize_current,project_snapshot
        raw=fixture()['data'];payload=project_snapshot(raw,ROOM);a=normalize_current(payload,ROOM)
        payload['person'].reverse();self.assertEqual(a['fingerprint'],normalize_current(payload,ROOM)['fingerprint'])
        del payload['record_totals'][P1]
        with self.assertRaises(ValueError):normalize_current(payload,ROOM)
        payload=project_snapshot(raw,ROOM);payload['person']*=1001
        with self.assertRaises(ValueError):normalize_current(payload,ROOM)
        raw['room'][0]['roster_version']=0
        self.assertIsNone(normalize_current(project_snapshot(raw,ROOM),ROOM)['summary']['total'])
