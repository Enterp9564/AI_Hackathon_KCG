"""Coordinates are diagram marks, not inferred diagnoses."""
import copy
import json
import unittest
from prototype.linkone_data import prepare, changes, evidence, project_payload
from prototype.tests.test_linkone_sync import fixture, ROOM, P1


def marked():
    raw = fixture()
    raw['data']['person'][0]['gender'] = 'MALE'
    raw['data']['person_state'][0]['chips'] = ['골절']
    raw['data']['person_event'][0].update(type='CHIP_ON', payload={
        'chip': '골절', 'body': {'points': [{'view': 0, 'x': 40, 'y': 58}]}})
    return raw


class BodyTests(unittest.TestCase):
    def test_projection_keeps_only_valid_coordinates_and_is_idempotent(self):
        p = {'chip': '골절', 'body': {'url': 'PRIVATE', 'points': [
            {'view': 0, 'x': 40, 'y': 58, 'extra': 'PRIVATE'},
            {'view': 0, 'x': True, 'y': 40}, {'view': 2, 'x': 50, 'y': 50},
            {'view': 0, 'x': float('nan'), 'y': 50}, {'view': 1, 'x': -1, 'y': 10}]}}
        actual = project_payload('CHIP_ON', p)
        self.assertEqual(actual['body']['points'], [{'view': 0, 'x': 40, 'y': 58}])
        self.assertNotIn('PRIVATE', json.dumps(actual))
        self.assertEqual(project_payload('CHIP_ON', actual), actual)
        self.assertEqual(project_payload('CHIP_ON', {'body': {'points': [{'view': 0.0, 'x': 40, 'y': 58}]}})['body']['points'][0]['view'], 0)
        self.assertEqual(len(project_payload('CHIP_ON', {'body': {'points': [{'view': 0, 'x': 40, 'y': 58}] * 41}})['body']['points']), 40)

    def test_front_back_laterality_and_abdominal_regions(self):
        from prototype.linkone_body import locate
        cases = [('MALE', 0, 40, 58, '우측 대퇴부'),
                 ('MALE', 0, 67, 58, '좌측 대퇴부'),
                 ('MALE', 1, 40, 60, '좌측 대퇴부'),
                 ('MALE', 1, 63, 60, '우측 대퇴부'),
                 ('MALE', 0, 53, 36, '상복부'), ('MALE', 0, 53, 42, '하복부'),
                 ('FEMALE', 0, 40, 58, '우측 대퇴부'),
                 ('FEMALE', 0, 50, 35, '상복부'), ('FEMALE', 0, 50, 40, '하복부')]
        for gender, view, x, y, label in cases:
            with self.subTest(gender=gender, view=view, label=label):
                r = locate(gender, {'view': view, 'x': x, 'y': y})
                self.assertEqual(r['label'], label)
                self.assertEqual(r['status'], 'mapped')

    def test_ambiguous_side_boundary_background_and_invalid(self):
        from prototype.linkone_body import locate
        side = locate('FEMALE', {'view': 1, 'x': 48, 'y': 60})
        self.assertIn('대퇴부', side['label']); self.assertIn('좌우 미확인', side['label'])
        r = locate('FEMALE', {'view': 1, 'x': 40, 'y': 34})
        self.assertEqual(r['status'], 'ambiguous')
        self.assertGreaterEqual(len(r['candidates']), 2)
        self.assertEqual(locate('MALE', {'view': 0, 'x': 53, 'y': 39})['status'], 'boundary')
        self.assertEqual(locate('MALE', {'view': 0, 'x': 2, 'y': 40})['status'], 'unmapped')
        self.assertEqual(locate('MALE', {'view': 9, 'x': 40, 'y': 58})['status'], 'invalid')

    def test_current_marks_follow_replace_off_undo_and_state_chips(self):
        from prototype.linkone_body import injury_context
        raw = marked(); data = raw['data']
        def add(i, typ, payload, undo=None):
            data['person_event'].append(dict(id=str(i), person_id=P1, room_id=ROOM,
                type=typ, payload=payload, undo_of=undo))
        add(2, 'CHIP_ON', {'chip': '골절', 'body': {'points': [{'view': 0, 'x': 53, 'y': 42}]}})
        self.assertEqual(injury_context(data)[P1]['current'][0]['locations'][0]['label'], '하복부')
        add(3, 'UNDO', {}, '2')
        self.assertEqual(injury_context(data)[P1]['current'][0]['locations'][0]['label'], '우측 대퇴부')
        add(4, 'CHIP_OFF', {'chip': '골절'})
        data['person_state'][0]['chips'] = []
        self.assertEqual(injury_context(data)[P1]['current'], [])
        add(5, 'UNDO', {}, '4'); data['person_state'][0]['chips'] = ['골절']
        self.assertEqual(injury_context(data)[P1]['current'][0]['event_id'], '1')

    def test_old_or_empty_marks_do_not_resurrect_old_coordinates(self):
        from prototype.linkone_body import injury_context
        raw = marked(); data = raw['data']
        e = copy.deepcopy(data['person_event'][0]); e.update(id='2', payload={'chip': '골절'})
        data['person_event'].append(e)
        self.assertEqual(injury_context(data)[P1]['current'][0]['locations'], [])
        self.assertEqual(injury_context(data)[P1]['current'][0]['status'], 'unrecorded')
        data['person_state'] = []
        self.assertEqual(injury_context(data)[P1]['current'], [])

    def test_baseline_evidence_includes_body_results_without_mutating_source(self):
        s = prepare(marked(), ROOM); s.update(id='test', revision=1, diff=changes(None, s))
        before = copy.deepcopy(s)
        result = json.loads(evidence(s)['content'])
        person = next(p for p in result['people'] if p['id'] == P1)
        self.assertEqual(person['injuries']['current'][0]['locations'][0]['label'], '우측 대퇴부')
        self.assertEqual(s, before)

    def test_projection_upgrade_is_not_presented_as_new_field_injury(self):
        old = prepare(fixture(), ROOM); old.pop('projection_version', None)
        new = prepare(marked(), ROOM); new.update(id='test', revision=2, diff=changes(old, new))
        result = json.loads(evidence(new)['content'])
        self.assertTrue(result['comparison']['projection_upgrade'])

    def test_gender_correction_and_canceled_correction_do_not_guess_old_template(self):
        from prototype.linkone_body import injury_context
        data = marked()['data']
        data['person'][0]['gender'] = 'FEMALE'
        data['person_event'].append(dict(id='2', person_id=P1, type='IDENTITY',
            payload={'changes': {'gender': {'from': 'MALE', 'to': 'FEMALE'}}}))
        self.assertEqual(injury_context(data)[P1]['current'][0]['status'], 'template_uncertain')
        data['person_event'].append(dict(id='3', person_id=P1, type='UNDO', undo_of='2'))
        data['person'][0]['gender'] = 'MALE'
        self.assertEqual(injury_context(data)[P1]['current'][0]['locations'][0]['label'], '우측 대퇴부')

    def test_undo_of_undo_and_bigint_order(self):
        from prototype.linkone_body import injury_context
        data = marked()['data']
        data['person_event'][0]['id'] = '9'
        data['person_event'] += [dict(id='10', person_id=P1, type='UNDO', undo_of='9'),
                                dict(id='11', person_id=P1, type='UNDO', undo_of='10')]
        self.assertEqual(injury_context(data)[P1]['current'][0]['event_id'], '9')
        self.assertFalse(injury_context(data)[P1]['current'][0]['canceled'])

    def test_different_people_are_isolated_and_invalid_marks_remain_unknown(self):
        from prototype.linkone_body import injury_context
        from prototype.tests.test_linkone_sync import P2
        data = marked()['data']
        data['person_state'].append(dict(person_id=P2, chips=['골절']))
        self.assertEqual(injury_context(data)[P2]['current'][0]['locations'], [])
        data['person_event'][0]['payload']['body']['points'] = [{'view': 0, 'x': 999, 'y': 58}]
        self.assertEqual(injury_context(data)[P1]['current'][0]['status'], 'unrecorded')
