import copy
import tempfile
import unittest
from pathlib import Path
from prototype.store import Store
from prototype.tests.test_linkone_sync import ROOM,OTHER,P1


def sample(room=ROOM):
    return dict(id='9007199254740993',room_id=room,person_id=P1,status='OK',urgency='IMMEDIATE',
        summary='가상 환자 상태 변화 · 현장 확인 필요',outcomes=['RECHECK'],pre_ktas={'state':'TEST'},
        reasons=[{'text':'가상 시험 근거'}],missing=[],based_on_event_id='21',last_event_id='21',
        based_on_at='2026-09-29T01:00:00+00:00',finished_at='2026-09-29T01:01:00+00:00')


class Source:
    def __init__(self):self.rows=[sample()];self.error=False;self.calls=0;self.after=None
    def poll(self,rooms,known):
        self.calls+=1
        if self.error:raise RuntimeError('private database details')
        result={r:{'fingerprint':'signature','rows':copy.deepcopy([x for x in self.rows if x['room_id']==r])} for r in rooms}
        if self.after:self.after()
        return result
    def close(self):pass


class AlertsTests(unittest.TestCase):
    def test_ended_patient_leaves_active_alerts_and_cannot_be_quoted(self):
        from prototype.store import Conflict
        self.alerts.tick();before=self.alerts.view(self.sid)['items'][0]
        self.source.rows[0].update(management='ENDED',last_event_id='22',management_updated_at='2026-09-29T01:02:00Z')
        self.alerts.tick();view=self.alerts.view(self.sid)
        self.assertEqual(view['items'],[]);self.assertEqual(view['unread'],0)
        self.assertEqual(view['ended_count'],1);self.assertEqual(view['missing_count'],0)
        self.assertEqual(view['ended_person_ids'],[P1])
        history=self.alerts.history(self.sid);self.assertEqual(len(history),2)
        for item in history:
            with self.assertRaises(Conflict):self.alerts.quote(self.sid,item['id'])
        self.source.error=True;self.alerts.tick()
        self.assertEqual(self.alerts.view(self.sid)['items'],[])
        self.source.error=False
        from prototype.patient_alerts import PatientAlerts
        restarted=PatientAlerts(self.store,self.source,start=False);self.addCleanup(restarted.close)
        self.assertEqual(restarted.view(self.sid)['ended_count'],1)
        self.source.rows[0].update(management='MANAGED',last_event_id='23',management_updated_at='2026-09-29T01:03:00Z')
        self.alerts.tick();view=self.alerts.view(self.sid)
        self.assertEqual(view['ended_count'],0);self.assertEqual(view['unread'],1)
        self.assertNotEqual(view['items'][0]['id'],before['id'])
        self.assertEqual(self.store.snapshot(self.sid)['runs'],[])

    def test_only_explicit_management_end_hides_alert(self):
        for status in (None,'MANAGED','UNRECOGNIZED'):
            self.source.rows[0]['management']=status;self.alerts.tick()
            self.assertEqual(len(self.alerts.view(self.sid)['items']),1)

    def setUp(self):
        from prototype.patient_alerts import PatientAlerts
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db');self.source=Source()
        self.sid=self.linked(ROOM);self.other=self.linked(OTHER)
        self.alerts=PatientAlerts(self.store,self.source,start=False)
        self.addCleanup(self.alerts.close)

    def linked(self,room):
        s=self.store.create_session('시험 사건')
        with self.store.db() as db:
            s['linkone']={'room_id':room,'status':'ready'};self.store._put_session(db,s)
        return s['id']

    def test_receive_isolated_idempotent_and_does_not_run_ai_or_change_facts(self):
        before=self.store.snapshot(self.sid)['session']
        self.alerts.tick();self.alerts.tick()
        view=self.alerts.view(self.sid)
        self.assertEqual(view['unread'],1);self.assertEqual(len(view['items']),1)
        self.assertEqual(view['items'][0]['original']['id'],'9007199254740993')
        self.assertEqual(self.alerts.view(self.other)['unread'],0)
        snap=self.store.snapshot(self.sid)
        self.assertEqual(snap['runs'],[]);self.assertEqual(snap['session'],before)

    def test_seen_survives_unchanged_poll_and_new_version_is_unread(self):
        self.alerts.tick();item=self.alerts.view(self.sid)['items'][0]
        self.alerts.seen(self.sid,item['id']);self.alerts.tick()
        self.assertEqual(self.alerts.view(self.sid)['unread'],0)
        self.source.rows[0]['summary']='정정된 가상 결과';self.alerts.tick()
        view=self.alerts.view(self.sid)
        self.assertEqual(view['unread'],1);self.assertNotEqual(view['items'][0]['id'],item['id'])
        self.assertEqual(len(self.alerts.history(self.sid)),2)

    def test_failure_preserves_last_success_and_backoff_is_bounded(self):
        self.alerts.tick();stamp=self.alerts.view(self.sid)['last_success_at']
        self.source.error=True
        delays=[self.alerts.tick() for _ in range(7)]
        self.assertEqual(delays,[6,12,24,48,60,60,60])
        view=self.alerts.view(self.sid)
        self.assertEqual(view['status'],'error');self.assertEqual(view['last_success_at'],stamp)
        self.assertEqual(len(view['items']),1);self.assertNotIn('private',str(view))
        self.source.error=False;self.assertEqual(self.alerts.tick(),2)

    def test_cross_room_response_fails_without_overwriting_good_data(self):
        self.alerts.tick()
        self.source.poll=lambda rooms,known:{ROOM:{'fingerprint':'wrong','rows':[sample(OTHER)]}}
        self.alerts.tick()
        self.assertEqual(self.alerts.view(self.sid)['status'],'error')
        self.assertEqual(self.alerts.view(self.sid)['unread'],1)

    def test_late_response_does_not_restore_deleted_session(self):
        self.source.after=lambda:self.store.delete_session(self.sid)
        self.alerts.tick()
        with self.assertRaises(KeyError):self.alerts.view(self.sid)

    def test_seen_and_quote_require_same_session_and_quote_is_stable(self):
        self.alerts.tick();item=self.alerts.view(self.sid)['items'][0]
        with self.assertRaises(KeyError):self.alerts.seen(self.other,item['id'])
        with self.assertRaises(KeyError):self.alerts.quote(self.other,item['id'])
        q=self.alerts.quote(self.sid,item['id'])
        self.assertIn('Link-One',q['prompt']);self.assertIn('확정',q['prompt'])
        self.assertEqual(q,self.alerts.quote(self.sid,item['id']))

    def test_no_linked_sessions_means_no_source_poll(self):
        self.store.delete_session(self.sid);self.store.delete_session(self.other)
        self.alerts.tick();self.assertEqual(self.source.calls,0)

    def test_restart_recovers_seen_and_requests_full_initial_sync(self):
        from prototype.patient_alerts import PatientAlerts
        self.alerts.tick();item=self.alerts.view(self.sid)['items'][0];self.alerts.seen(self.sid,item['id'])
        rebuilt=PatientAlerts(self.store,self.source,start=False);self.addCleanup(rebuilt.close)
        self.assertEqual(rebuilt.view(self.sid)['unread'],0)
        self.assertEqual(rebuilt.known,{})

    def test_removed_result_is_not_resolved_and_unknown_urgency_is_retained(self):
        self.source.rows[0]['urgency']='FUTURE_CODE';self.alerts.tick()
        self.assertEqual(self.alerts.view(self.sid)['items'][0]['original']['urgency'],'FUTURE_CODE')
        self.source.rows=[];self.alerts.tick()
        view=self.alerts.view(self.sid)
        self.assertEqual(view['unread'],0);self.assertEqual(view['missing_count'],1)
        self.assertEqual(len(self.alerts.history(self.sid)),1)

    def test_oversized_or_duplicate_results_rejected(self):
        self.source.rows=[sample(),sample()];self.alerts.tick()
        self.assertEqual(self.alerts.view(self.sid)['status'],'error')
        self.assertEqual(self.alerts.view(self.sid)['items'],[])

    def test_recreated_room_does_not_reuse_old_cursor(self):
        self.alerts.tick();self.store.delete_session(self.sid);self.sid=self.linked(ROOM)
        def poll(rooms,known):
            self.assertNotIn(ROOM,known)
            return {r:{'fingerprint':'signature','rows':[sample()] if r==ROOM else []} for r in rooms}
        self.source.poll=poll;self.alerts.tick()
        self.assertEqual(self.alerts.view(self.sid)['unread'],1)

    def test_slow_or_concurrent_poll_is_not_enqueued(self):
        self.alerts.poll_lock.acquire()
        try:self.assertEqual(self.alerts.tick(),2)
        finally:self.alerts.poll_lock.release()
        self.assertEqual(self.source.calls,0)

    def test_quote_stays_same_when_session_title_changes(self):
        self.alerts.tick();item=self.alerts.view(self.sid)['items'][0];first=self.alerts.quote(self.sid,item['id'])
        with self.store.db() as db:
            s=self.store._session(db,self.sid);s['title']='정정 사건';self.store._put_session(db,s)
        self.assertEqual(first,self.alerts.quote(self.sid,item['id']))


class AlertsHTTPTests(unittest.TestCase):
    def test_receive_seen_review_are_isolated_and_repeated_review_runs_once(self):
        import threading,json,urllib.request,urllib.error
        from prototype.engine import Engine
        from prototype.models import DemoModel
        from prototype.server import make_server
        from prototype.tests.test_linkone_sync import Source as LegacySource
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');engine=Engine(store,demo_model=DemoModel(.001))
            server=make_server(store,engine,0,linkone_source=LegacySource())
            from prototype.tests.test_vessel_alerts import CombinedSource
            server.patient_alerts.source=CombinedSource()
            threading.Thread(target=server.serve_forever,daemon=True).start()
            base=f'http://127.0.0.1:{server.server_port}'
            token=''
            def request(path,data=None,auth=None):
                req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,
                    headers={'Content-Type':'application/json','X-Session-Token':token if auth is None else auth})
                try:
                    with urllib.request.urlopen(req) as r:return r.status,json.load(r)
                except urllib.error.HTTPError as e:return e.code,json.load(e)
            try:
                token=request('/api/config')[1]['token']
                s=store.create_session('가상 알림 시험');other=store.create_session('다른 사건')
                with store.db() as db:
                    s['linkone']={'room_id':ROOM,'status':'ready'};store._put_session(db,s)
                server.patient_alerts.tick();path='/api/sessions/'+s['id']
                code,view=request(path+'/patient-alerts');self.assertEqual(code,200)
                vessel=view['vessel']['items'][0]
                self.assertEqual(request(path+'/vessel-alert-seen',{'alert_id':vessel['id']},'bad')[0],403)
                self.assertEqual(request('/api/sessions/'+other['id']+'/vessel-alert-seen',{'alert_id':vessel['id']})[0],404)
                self.assertEqual(request(path+'/vessel-alert-seen',{'alert_id':vessel['id']})[0],200)
                self.assertEqual(request(path+'/patient-alerts')[1]['vessel']['unread'],0)
                self.assertEqual(server.patient_alerts.source.vessel_rows[0]['ack_count'],0)
                item=view['items'][0]
                self.assertEqual(store.snapshot(s['id'])['runs'],[])
                self.assertEqual(request(path+'/patient-alert-seen',{'alert_id':item['id']},'bad')[0],403)
                self.assertEqual(request('/api/sessions/'+other['id']+'/patient-alert-review',{'alert_id':item['id']})[0],404)
                self.assertEqual(request(path+'/patient-alert-seen',{'alert_id':item['id']})[0],200)
                a=request(path+'/patient-alert-review',{'alert_id':item['id']});self.assertEqual(a[0],202)
                b=request(path+'/patient-alert-review',{'alert_id':item['id']});self.assertEqual(a[1]['id'],b[1]['id'])
                engine.wait(a[1]['id']);self.assertEqual(len(store.snapshot(s['id'])['runs']),1)
                self.assertEqual(request(path+'/message',{'prompt':'forged','kind':'analysis','request_id':'patient-alert:forged'})[0],400)
            finally:server.shutdown();server.server_close();engine.close()


class WorkerTests(unittest.TestCase):
    def test_bind_failure_never_starts_poller(self):
        from unittest.mock import patch,MagicMock
        from prototype.server import make_server
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db')
            with patch('prototype.server.ThreadingHTTPServer.__init__',side_effect=OSError('occupied')),patch('prototype.patient_alerts.PatientAlerts.start') as start:
                with self.assertRaises(OSError):make_server(store,MagicMock(),0)
                start.assert_not_called()

    def test_shutdown_during_process_creation_terminates_worker(self):
        from prototype.linkone_alert_source import AlertSource
        from unittest.mock import patch,MagicMock
        import threading,time
        entered=threading.Event();release=threading.Event();source=AlertSource();proc=MagicMock();proc.pid=999999
        proc.stdout.fileno.return_value=17
        def spawn(*args,**kwargs):entered.set();release.wait(2);return proc
        def poll():
            try:source.poll([ROOM],{})
            except Exception:pass
        with patch('prototype.linkone_alert_source.subprocess.Popen',side_effect=spawn),patch('prototype.linkone_alert_source.os.killpg') as kill,patch('prototype.linkone_alert_source.select.select',return_value=([proc.stdout],[],[])),patch('prototype.linkone_alert_source.os.read',return_value=b'{}\n'):
            t=threading.Thread(target=poll);t.start();self.assertTrue(entered.wait(2))
            closer=threading.Thread(target=source.shutdown);closer.start()
            self.assertTrue(source.stopped.wait(2));release.set();t.join(2);closer.join(2)
            self.assertFalse(t.is_alive());self.assertFalse(closer.is_alive())
            self.assertIsNone(source.proc);kill.assert_called_once()

    def test_permanent_shutdown_prevents_new_process_and_recoverable_close_does_not(self):
        from prototype.linkone_alert_source import AlertSource
        from unittest.mock import patch
        source=AlertSource();source.shutdown()
        with patch('prototype.linkone_alert_source.subprocess.Popen') as popen:
            with self.assertRaises(RuntimeError):source.poll([ROOM],{})
            popen.assert_not_called()
        source=AlertSource();source.close()
        self.assertFalse(source.stopped.is_set())
