import unittest
from prototype.ship_tilt import assess_tilt


class TiltTests(unittest.TestCase):
    now = 1800001200

    def row(self, timestamp, roll, trim=0, ident=1):
        from datetime import datetime, timezone
        return dict(id=ident, measured_at=datetime.fromtimestamp(timestamp, timezone.utc).isoformat(), roll=roll, trim=trim)

    def test_image_example_is_measurement_not_automatic_alarm(self):
        result = assess_tilt([self.row(self.now-1200, 6), self.row(self.now-720, 9, ident=2)], self.now)
        self.assertEqual(result['measurement_source']['type'], 'field_instrument')
        self.assertEqual(result['measurement_source']['basis'], 'user_confirmed_linkone_workflow')
        self.assertEqual(result['age_seconds'], 720)
        self.assertEqual(result['change']['elapsed_seconds'], 480)
        self.assertEqual(result['change']['roll']['magnitude_delta_deg'], 3)
        self.assertEqual(result['change']['roll']['average_magnitude_deg_per_min'], .375)
        self.assertEqual(result['operational_alarm_thresholds'], None)
        self.assertIn('damage_equilibrium_7', result['numeric_reference_matches']['roll'])
        self.assertNotIn('passenger_intact_10', result['numeric_reference_matches']['roll'])

    def test_signed_angle_reduction_and_timestamp_order(self):
        result = assess_tilt([self.row(self.now-60, -3.3, ident=1), self.row(self.now-120, -9.9, ident=99)], self.now)
        self.assertAlmostEqual(result['change']['roll']['magnitude_delta_deg'], -6.6)
        self.assertEqual(result['latest']['roll_direction'], '좌현')
        self.assertEqual(result['latest']['id'], 1)

    def test_direction_crossing_not_magnitude_worsening(self):
        result = assess_tilt([self.row(self.now-120, -9), self.row(self.now-60, 9)], self.now)
        self.assertTrue(result['change']['roll']['direction_crossed'])
        self.assertEqual(result['change']['roll']['magnitude_delta_deg'], 0)
        self.assertEqual(result['change']['roll']['signed_delta_deg'], 18)

    def test_invalid_and_future_samples_do_not_become_latest(self):
        rows = [self.row(self.now-60, 9), self.row(self.now+1, 20), self.row(self.now-30, float('nan'), None),
                dict(measured_at='2026-09-28T12:00:00', roll=20), self.row(self.now-1, True, None)]
        result = assess_tilt(rows, self.now)
        self.assertEqual(result['excluded_rows'], 4)
        self.assertEqual(result['age_seconds'], 60)
        self.assertIsNone(result['change'])

    def test_simultaneous_samples_do_not_generate_rate(self):
        result = assess_tilt([self.row(self.now-60, 5), self.row(self.now-60, 7)], self.now)
        self.assertIsNone(result['change'])
        self.assertTrue(result['latest_time_ambiguous'])

    def test_design_comparisons_do_not_assign_risk_or_trim_five_limit(self):
        result = assess_tilt([self.row(self.now-60, 15, 5)], self.now)
        self.assertIn('damage_equilibrium_15', result['numeric_reference_matches']['roll'])
        self.assertEqual(result['numeric_reference_matches']['trim'], [])
        self.assertNotIn('risk_level', result)
        result = assess_tilt([self.row(self.now-60, 22.5, -10)], self.now)
        self.assertIn('machinery_dynamic_pitch_7_5', result['numeric_reference_matches']['trim'])
        self.assertEqual(result['latest']['trim_direction'], '선수 내려감')

    def test_empty_and_partial_measurements(self):
        self.assertIsNone(assess_tilt([], self.now)['latest'])
        result = assess_tilt([self.row(self.now-60, 9, None)], self.now)
        self.assertEqual(result['latest']['roll'], 9)
        self.assertIsNone(result['latest']['trim_direction'])
        self.assertEqual(result['partial_rows'], 1)

    def test_assessment_survives_compact_evidence_budget_without_mutating_source(self):
        import copy
        import json
        from unittest.mock import patch
        from prototype.linkone_data import prepare, changes, evidence
        from prototype.tests.test_linkone_sync import fixture, ROOM
        payload = fixture()
        payload['data']['hull_tilt'] = [dict(self.row(self.now-1000+i, i/10, ident=i), room_id=ROOM) for i in range(100)]
        snapshot = prepare(payload, ROOM)
        snapshot.update(id='tilt-test', revision=1, diff=changes(None, snapshot))
        before = copy.deepcopy(snapshot)
        with patch('prototype.ship_tilt.time.time', return_value=self.now):
            content = json.loads(evidence(snapshot)['content'])
        self.assertGreater(content['current_omitted']['hull_tilt'], 0)
        self.assertEqual(content['tilt_assessment']['source_rows'], 100)
        self.assertEqual(content['tilt_assessment']['latest']['id'], 99)
        self.assertEqual(snapshot, before)
