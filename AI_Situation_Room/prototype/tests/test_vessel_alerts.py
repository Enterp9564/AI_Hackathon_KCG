import copy
import tempfile
import unittest
from pathlib import Path
from prototype.store import Store
from prototype.patient_alerts import PatientAlerts
from prototype.tests.test_patient_alerts import Source
from prototype.tests.test_linkone_sync import ROOM, OTHER


def vessel_sample():
    return dict(id='100', room_id=ROOM, kind='LEVEL', axis='ROLL', level_deg=10.0,
                hull_tilt_id='50', roll=10.2, trim=1.0, measured_at='2026-09-29T01:00:00+00:00',
                prev_roll=None, prev_trim=None, prev_measured_at=None,
                title='가상 경사 경고', message='가상 출처 내용', basis='가상 기준', note=None,
                standard=None, raised_at='2026-09-29T01:01:00+00:00', ack_count=0, last_acked_at=None)


class CombinedSource(Source):
    def __init__(self):
        super().__init__(); self.vessel_rows=[vessel_sample()]; self.vessel_error=False

    def poll(self, rooms, known):
        result=super().poll(rooms, known)
        for room in rooms:
            result[room]['vessel']={'error':True} if self.vessel_error else dict(
                fingerprint=str(self.vessel_rows), rows=copy.deepcopy([r for r in self.vessel_rows if r['room_id']==room]), truncated=False)
        return result


class VesselAlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db');self.source=CombinedSource()
        self.service=PatientAlerts(self.store,source=self.source,start=False)
        self.sid=self.link(ROOM);self.other=self.link(OTHER)

    def link(self, room):
        s=self.store.create_session('가상 사건')
        with self.store.db() as db:s['linkone']={'room_id':room};self.store._put_session(db,s)
        return s['id']

    def test_receive_deduplicates_isolates_and_cannot_run_ai(self):
        before=self.store.snapshot(self.sid)['session'];self.service.tick()
        first=self.service.view(self.sid)['vessel'];self.assertEqual(first['unread'],1)
        self.assertEqual(self.service.view(self.other)['vessel']['items'],[])
        self.service.tick();self.assertEqual(self.service.view(self.sid)['vessel']['items'],first['items'])
        self.assertEqual(self.store.snapshot(self.sid)['session'],before)
        self.assertEqual(self.store.snapshot(self.sid)['runs'],[])

    def test_read_does_not_ack_remote_and_changed_source_reopens(self):
        self.service.tick();a=self.service.view(self.sid)['vessel']['items'][0]
        self.service.vessels.seen(self.sid,a['id']);self.assertEqual(self.source.vessel_rows[0]['ack_count'],0)
        with self.assertRaises(KeyError):self.service.vessels.seen(self.other,a['id'])
        self.source.vessel_rows[0]['ack_count']=1;self.source.vessel_rows[0]['last_acked_at']='2026-09-29T01:05:00+00:00'
        self.service.tick();b=self.service.view(self.sid)['vessel']['items'][0]
        self.assertNotEqual(a['id'],b['id']);self.assertIsNone(b['seen_at'])
        self.assertEqual(b['original']['ack_count'],1)

    def test_vessel_failure_keeps_history_without_blocking_patients(self):
        self.service.tick();before=self.service.view(self.sid)['vessel']['items']
        self.source.vessel_error=True;self.source.rows[0]['summary']='환자 새 내용'
        self.service.tick();view=self.service.view(self.sid)
        self.assertEqual(view['status'],'ready');self.assertEqual(view['vessel']['status'],'error')
        self.assertEqual(view['vessel']['items'],before);self.assertEqual(view['items'][0]['original']['summary'],'환자 새 내용')

    def test_invalid_room_rejected_and_disappearance_is_not_resolution(self):
        self.service.tick();self.source.vessel_rows=[];self.service.tick()
        self.assertEqual(self.service.view(self.sid)['vessel']['missing_count'],1)
        from prototype.vessel_alerts import normalize
        row=vessel_sample();row['room_id']=OTHER
        with self.assertRaises(ValueError):normalize([row],ROOM)

    def test_restart_exposes_waiting_not_live_success(self):
        self.service.tick();fresh=PatientAlerts(self.store,source=CombinedSource(),start=False)
        self.assertEqual(fresh.view(self.sid)['vessel']['status'],'waiting')
        self.assertEqual(len(fresh.view(self.sid)['vessel']['items']),1)

    def test_unchanged_packet_retains_local_read_and_shared_room_session_is_populated(self):
        self.service.tick();item=self.service.view(self.sid)['vessel']['items'][0]
        self.service.vessels.seen(self.sid,item['id']);old=self.source.poll
        def poll(rooms,known):
            result=old(rooms,known)
            for r in rooms:
                p=result[r]['vessel']
                if known.get('vessel:'+r)==p['fingerprint']:p['rows']=None
            return result
        self.source.poll=poll;self.service.tick();self.assertEqual(self.service.view(self.sid)['vessel']['unread'],0)
        another=self.link(ROOM);self.service.tick()
        self.assertEqual(self.service.view(another)['vessel']['unread'],1)
        self.assertEqual(self.service.view(self.sid)['vessel']['unread'],0)

    def test_room_change_hides_cached_alerts_before_next_poll(self):
        self.service.tick()
        with self.store.db() as db:
            s=self.store._session(db,self.sid);s['linkone']['room_id']=OTHER;self.store._put_session(db,s)
        self.assertEqual(self.service.view(self.sid)['vessel']['items'],[])
        self.assertEqual(self.service.view(self.sid)['vessel']['status'],'waiting')
