"""Isolated synthetic data only; never connects to Link-One or a LIVE model."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
from prototype.store import Store
from prototype.engine import Engine
from prototype.models import DemoModel
from prototype.server import make_server
from prototype.tests.test_patient_alerts import Source, sample
from prototype.tests.test_linkone_sync import ROOM, OTHER


def main():
    with TemporaryDirectory(prefix='haeon-patient-p0-') as folder:
        store = Store(Path(folder) / 'room.sqlite')
        engine = Engine(store, demo_model=DemoModel(.01))
        for title, room in [('가상 환자 8명 점검', ROOM), ('다른 가상 사건', OTHER)]:
            session = store.create_session(title)
            with store.db() as db:
                session['linkone'] = {'room_id': room, 'status': 'ready'}
                store._put_session(db, session)
        if os.environ.get('HAEON_TEST_VESSEL') == '1':
            from prototype.tests.test_vessel_alerts import CombinedSource, vessel_sample
            source=CombinedSource()
            rapid=vessel_sample();rapid.update(kind='RAPID',title='가상 선체 급변 경고',raised_at='2026-09-29T03:00:00+00:00')
            stale=vessel_sample();stale.update(id='101',kind='STALE',title='가상 측정 지연 경고',raised_at='2026-09-29T04:00:00+00:00',ack_count=1,last_acked_at='2026-09-29T04:05:00+00:00')
            source.vessel_rows=[rapid,stale]
        else:
            source = Source()
        source.rows = []
        for number in range(8):
            row = sample()
            row.update(id=str(number + 100), person_id=f'{number + 1:08d}-0000-0000-0000-000000000000',
                       urgency='IMMEDIATE' if number < 5 else 'WITHIN_30' if number < 7 else 'OBSERVE',
                       summary=f'가상 환자 {chr(65 + number)} · 현장 상태와 판정 기준을 확인하세요.')
            if os.environ.get('HAEON_TEST_VESSEL')=='1':row['finished_at']=f'2026-09-29T01:{number+20:02d}:00+00:00'
            source.rows.append(row)
        server = make_server(store, engine, 0, alert_source=source)
        print(f'PATIENT_UI http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
            engine.close()


if __name__ == '__main__':
    main()
