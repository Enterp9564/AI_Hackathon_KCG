import copy
import tempfile
import unittest
from pathlib import Path
from prototype.store import Store, Conflict
from prototype.engine import Engine
from prototype.models import DemoModel

ROOM='90ed5b9d-3804-4a73-83d9-3b1e91881f9d'
OTHER='4957a3fb-b012-4e9a-87e1-57b4301cf6b9'
P1='11111111-1111-4111-8111-111111111111'
P2='22222222-2222-4222-8222-222222222222'


def fixture(room_id=ROOM):
    from prototype.linkone_data import TABLES
    data={t:[] for t in TABLES}
    data['room']=[dict(id=room_id,name='시험선 침수',case_no='TEST-1',mode='REAL',status='ACTIVE',roster_version=1,roster_total=None,expected_count=None,waters='시험 해역')]
    data['person']=[dict(id=P1,room_id=room_id,name='시험 승객 A',age=20,kind='PASSENGER',off_roster=False),dict(id=P2,room_id=room_id,name='시험 승객 B',age=40,kind='PASSENGER',off_roster=False)]
    data['person_state']=[dict(person_id=P1,room_id=room_id,rescue='RESCUED_ON_SHIP',transit='NONE',management='MANAGED',location_kind='SHIP',severity='URGENT',last_event_id='1')]
    data['person_event']=[dict(id='1',room_id=room_id,person_id=P1,type='RESCUE',payload={},server_at='2026-09-28T00:00:00Z',undo_of=None)]
    return {'room_id':room_id,'data':data,'received_at':123.0,'revisions':{'before':{},'after':{}},'complete':True}


class DataTests(unittest.TestCase):
    def data_module(self):
        from prototype import linkone_data
        return linkone_data

    def test_feature_available(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('prototype.linkone_data'),'new snapshot data contract is not implemented')

    def test_summary_tracks_unrecorded_states_without_inventing_location(self):
        d=self.data_module();snap=d.prepare(fixture(),ROOM)
        self.assertEqual(snap['summary']['total'],2)
        self.assertEqual(snap['summary']['rescued'],1)
        self.assertEqual(snap['summary']['unrecorded'],1)
        self.assertEqual(snap['summary']['on_ship'],1)
        self.assertEqual(snap['summary']['locations'],{'SHIP':1,'UNKNOWN':1})

    def test_empty_unavailable_roster_stays_unknown(self):
        d=self.data_module();s=fixture();s['data']['person']=[];s['data']['person_state']=[];s['data']['person_event']=[];s['data']['room'][0]['roster_version']=0
        self.assertIsNone(d.prepare(s,ROOM)['summary']['total'])

    def test_excluded_and_merged_people_not_double_counted(self):
        d=self.data_module();s=fixture();s['data']['person'][1]['merged_into_id']=P1
        self.assertEqual(d.prepare(s,ROOM)['summary']['total'],1)

    def test_cross_room_or_incomplete_snapshot_rejected(self):
        d=self.data_module();s=fixture();s['data']['person'][0]['room_id']=OTHER
        with self.assertRaises(ValueError):d.prepare(s,ROOM)
        s=fixture();s['complete']=False
        with self.assertRaises(ValueError):d.prepare(s,ROOM)
        s=fixture();del s['data']['person_event']
        with self.assertRaises(ValueError):d.prepare(s,ROOM)

    def test_duplicate_and_dangling_reference_rejected(self):
        d=self.data_module();s=fixture();s['data']['person'].append(copy.deepcopy(s['data']['person'][0]))
        with self.assertRaises(ValueError):d.prepare(s,ROOM)
        s=fixture();s['data']['person_state'][0]['last_event_id']='99'
        with self.assertRaises(ValueError):d.prepare(s,ROOM)

    def test_hash_ignores_fetch_time_and_row_order_but_diff_sees_correction(self):
        d=self.data_module();a=d.prepare(fixture(),ROOM);s=fixture();s['received_at']=999;s['data']['person'].reverse()
        self.assertEqual(a['hash'],d.prepare(s,ROOM)['hash'])
        s['data']['person'][0]['name']='정정된 이름'
        b=d.prepare(s,ROOM);diff=d.changes(a,b)
        self.assertEqual(diff['changed_count'],1)
        self.assertEqual(diff['tables']['person']['changed'][0]['fields']['name']['before'],'시험 승객 B')
        self.assertNotEqual(a['hash'],b['hash'])

    def test_undo_and_removal_are_preserved(self):
        d=self.data_module();a=d.prepare(fixture(),ROOM);s=fixture()
        s['data']['person_event'].append(dict(id='2',room_id=ROOM,person_id=P1,type='UNDO',payload={},undo_of='1'))
        s['data']['person_state'][0].update(rescue='UNRESCUED',last_event_id='2')
        s['data']['person'].pop()
        b=d.prepare(s,ROOM);diff=d.changes(a,b)
        self.assertEqual(diff['added_count'],1);self.assertEqual(diff['removed_count'],1)
        self.assertEqual(b['summary']['rescued'],0)
        self.assertEqual(a['summary']['rescued'],1)


class Source:
    def __init__(self):self.payload=fixture();self.fail=False
    def rooms(self):return [{'id':ROOM,'name':'시험선 침수','mode':'REAL','status':'ACTIVE'}]
    def fetch(self,room_id):
        if self.fail:raise RuntimeError('sensitive fake failure')
        s=copy.deepcopy(self.payload)
        if room_id!=s['room_id']:s=fixture(room_id)
        return s


class ServiceTests(unittest.TestCase):
    def setUp(self):
        from prototype.linkone_sync import LinkOneSync
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db.sqlite');self.source=Source()
        self.engine=Engine(self.store,demo_model=DemoModel(delay=.001));self.addCleanup(self.engine.close)
        self.sync=LinkOneSync(self.store,self.engine,self.source);self.addCleanup(self.sync.close)

    def receive(self,room=ROOM):
        session=self.sync.connect(room,'demo');self.sync.wait(session['id']);return session['id']

    def test_same_room_uses_one_session_and_same_data_does_not_repeat_ai(self):
        sid=self.receive();snap=self.store.snapshot(sid)
        self.engine.wait(snap['session']['linkone']['analysis_run_id'])
        self.assertEqual(snap['session']['facts']['total'],2)
        self.assertEqual(len(snap['runs']),1)
        again=self.receive();self.assertEqual(sid,again)
        self.assertEqual(len(self.store.list_sessions()),1)
        self.assertEqual(len(self.store.snapshot(sid)['runs']),1)
        self.assertEqual(self.sync.view(sid)['revision'],1)

    def test_changed_data_retains_before_after_and_new_analysis(self):
        sid=self.receive();self.engine.wait(self.sync.view(sid)['analysis_run_id'])
        self.source.payload['data']['person'][1]['name']='새 이름'
        self.sync.sync(sid);self.sync.wait(sid)
        self.assertEqual(self.sync.view(sid)['revision'],2)
        self.assertEqual(len(self.sync.history(sid)),2)
        self.assertEqual(self.sync.details(sid)['diff']['changed_count'],1)
        self.engine.wait(self.sync.view(sid)['analysis_run_id'])
        self.assertEqual(len(self.store.snapshot(sid)['runs']),2)

    def test_fetch_failure_keeps_prior_source_and_sanitizes_error(self):
        sid=self.receive();self.engine.wait(self.sync.view(sid)['analysis_run_id'])
        before=self.sync.details(sid)
        self.source.fail=True;self.sync.sync(sid);self.sync.wait(sid)
        self.assertEqual(self.sync.details(sid)['hash'],before['hash'])
        self.assertEqual(self.sync.view(sid)['status'],'failed')
        self.assertNotIn('sensitive',self.sync.view(sid)['error'])

    def test_other_room_has_separate_session_and_evidence(self):
        a=self.receive();b=self.receive(OTHER)
        self.assertNotEqual(a,b)
        self.assertEqual(self.sync.details(a)['room_id'],ROOM)
        self.assertEqual(self.sync.details(b)['room_id'],OTHER)

    def test_source_session_prevents_user_and_model_fact_overwrite(self):
        sid=self.receive();self.engine.wait(self.sync.view(sid)['analysis_run_id'])
        s=self.store.snapshot(sid)
        with self.assertRaises(Conflict):self.store.set_facts(sid,{'total':999},s['session']['version'])
        with self.assertRaises(Conflict):self.store.apply_update(s['runs'][0]['id'],{'total':999},s['session']['version'])
        from prototype.tools import evidence_for
        evidence=evidence_for(s,'상황 검토')
        self.assertTrue(any(e.get('linkone_snapshot_id') for e in evidence))

    def test_busy_sync_protects_deletion_and_messages(self):
        import threading
        entered=threading.Event();release=threading.Event();original=self.source.fetch
        def blocking(room):entered.set();release.wait(3);return original(room)
        self.source.fetch=blocking
        sid=self.sync.connect(ROOM,'demo')['id'];entered.wait(2)
        try:
            with self.assertRaises(Conflict):self.store.delete_session(sid)
            with self.assertRaises(Conflict):self.store.enqueue(sid,'지금','analysis','','x')
            with self.assertRaises(Conflict):self.sync.sync(sid)
        finally:release.set();self.sync.wait(sid)

    def test_reconnect_honors_selected_mode(self):
        sid=self.receive();self.engine.wait(self.sync.view(sid)['analysis_run_id'])
        self.sync.connect(ROOM,'live');self.sync.wait(sid)
        self.assertEqual(self.store.snapshot(sid)['session']['mode'],'live')
        self.sync.connect(ROOM,'demo');self.sync.wait(sid)
        self.assertEqual(self.store.snapshot(sid)['session']['mode'],'demo')

    def test_dispatch_failure_does_not_leave_permanent_queued_run(self):
        from unittest.mock import patch
        with patch.object(self.engine,'submit',side_effect=RuntimeError('dispatch stopped')):
            sid=self.receive()
        self.assertEqual(self.sync.view(sid)['status'],'failed')
        self.assertEqual(self.store.snapshot(sid)['runs'][0]['status'],'failed')
        run=self.sync.analyze(sid);self.engine.wait(run['id'])
        self.assertEqual(self.store.get_run(run['id'])['status'],'completed')

    def test_restart_marks_incomplete_receive_and_preserves_previous_snapshot(self):
        sid=self.receive();self.engine.wait(self.sync.view(sid)['analysis_run_id'])
        prior=self.sync.details(sid)['hash']
        with self.store.db() as db:
            s=self.store._session(db,sid);s['linkone']['status']='receiving';self.store._put_session(db,s)
        from prototype.linkone_sync import LinkOneSync
        recovered=LinkOneSync(self.store,self.engine,self.source)
        try:
            self.assertEqual(recovered.view(sid)['status'],'interrupted')
            self.assertEqual(recovered.details(sid)['hash'],prior)
        finally:recovered.close()

    def test_user_followup_cannot_change_source_and_always_has_current_evidence(self):
        sid=self.receive();self.engine.wait(self.sync.view(sid)['analysis_run_id'])
        original=self.store.snapshot(sid)['session']['facts'].copy()
        run=self.engine.submit(sid,'총원을 999명으로 정정하고 분석','analysis','','followup')
        self.engine.wait(run['id'])
        self.assertEqual(self.store.snapshot(sid)['session']['facts'],original)
        self.assertEqual(self.store.get_run(run['id'])['linkone_snapshot_id'],self.sync.details(sid)['id'])

class AdditionalDataTests(unittest.TestCase):
    def test_identity_and_close_payload_excludes_unselected_contact_fields(self):
        from prototype.linkone_data import prepare
        s=fixture();event=s['data']['person_event'][0]
        event.update(type='IDENTITY',payload={'changes':{'name':{'from':'A','to':'B'},'tel':{'from':None,'to':'PRIVATE'},'birth':{'from':None,'to':'PRIVATE'}}})
        result=prepare(s,ROOM)
        self.assertNotIn('PRIVATE',str(result));self.assertIn('name',result['data']['person_event'][0]['payload']['changes'])
        event.update(type='CLOSE',payload={'tel':'PRIVATE','address':'PRIVATE','placeName':'구호소'})
        self.assertNotIn('PRIVATE',str(prepare(s,ROOM)))

    def test_field_only_people_do_not_establish_complete_roster(self):
        from prototype.linkone_data import prepare
        s=fixture();s['data']['room'][0]['roster_version']=0
        for p in s['data']['person']:p['off_roster']=True
        summary=prepare(s,ROOM)['summary']
        self.assertIsNone(summary['total']);self.assertEqual(summary['known_people'],2)

    def test_latest_numeric_measurement_reaches_model(self):
        from prototype.linkone_data import prepare,changes,evidence
        import json
        s=fixture();s['data']['hull_tilt']=[{'id':str(i),'room_id':ROOM,'roll':i,'trim':0} for i in range(1,102)]
        snap=prepare(s,ROOM);snap.update(id='test',revision=1,diff=changes(None,snap))
        context=json.loads(evidence(snap)['content'])
        self.assertEqual(context['current']['hull_tilt'][-1]['id'],'101')
