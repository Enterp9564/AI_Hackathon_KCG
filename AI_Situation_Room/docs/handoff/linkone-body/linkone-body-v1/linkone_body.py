"""Versioned diagram-region lookup. No image model, network or clinical inference."""
import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

BODY_CHIPS = frozenset(('출혈', '골절', '열상', '자상', '절단', '찰과상', '타박상', '화상'))


@lru_cache(maxsize=1)
def atlas():
    return json.loads((Path(__file__).parent / 'knowledge/linkone-body-regions.json').read_text())


def valid_point(p):
    return (isinstance(p, dict) and type(p.get('view')) in (int, float) and p['view'] in (0, 1)
            and all(type(p.get(k)) in (int, float) and math.isfinite(p[k]) and 0 <= p[k] <= 100
                    for k in ('x', 'y')))


def project_body(body):
    """Keep bounded coordinates only; never include URL/image/extra nested fields."""
    if not isinstance(body, dict) or not isinstance(body.get('points'), list):
        return None
    return {'points': [{k: p[k] for k in ('view', 'x', 'y')}
                       for p in body['points'][:40] if valid_point(p)]}


def segment_distance(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    norm = dx * dx + dy * dy
    t = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / norm)) if norm else 0
    return math.hypot(x - a[0] - t * dx, y - a[1] - t * dy)


def polygon_test(x, y, polygon):
    inside = False
    distance = float('inf')
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        distance = min(distance, segment_distance(x, y, a, b))
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0]) * (y-a[1]) / (b[1]-a[1]) + a[0]:
            inside = not inside
    return inside or distance < 1e-8, distance


def locate(gender, point):
    if not valid_point(point):
        return {'status': 'invalid', 'label': '좌표 확인 필요', 'candidates': []}
    female = gender == 'FEMALE'
    template = ('female-' + ('front' if point['view'] == 0 else 'side') if female
                else 'male-' + ('front' if point['view'] == 0 else 'back'))
    model = atlas()
    matches, nearby = [], []
    for region in model['templates'][template]['regions']:
        inside, distance = polygon_test(point['x'], point['y'], region['polygon'])
        item = {'code': region['code'], 'label': region['label']}
        if inside:
            matches.append(item)
        if distance <= model['boundary_margin']:
            nearby.append(item)
    if len(matches) > 1:
        status, candidates = 'ambiguous', matches
    elif nearby:
        status = 'boundary'
        candidates = matches + [r for r in nearby if r not in matches]
    elif matches:
        status, candidates = 'mapped', matches
    else:
        status, candidates = 'unmapped', []
    label = ' / '.join(c['label'] for c in candidates) or '부위 확인 필요'
    if status in ('boundary', 'ambiguous'):
        label += ' · 경계 확인' if status == 'boundary' else ' · 겹침 확인'
    return dict(point={k: point[k] for k in ('view', 'x', 'y')}, template=template,
                template_basis='recorded_gender' if gender in ('MALE', 'FEMALE') else 'linkone_default_male',
                status=status, label=label, candidates=candidates)


def event_order(event):
    # PostgreSQL bigint may be a JSON string. Never compare it lexicographically.
    value = str(event.get('id', ''))
    return int(value) if value.isdigit() else -1


def injury_context(data):
    """Current state gates event-derived marks; retain a short auditable history."""
    grouped = defaultdict(list)
    for event in data.get('person_event', []):
        grouped[event.get('person_id')].append(event)
    states = {s['person_id']: s for s in data.get('person_state', [])}
    result = {}
    for person in data.get('person', []):
        pid = person['id']
        events = sorted(grouped[pid], key=event_order)
        canceled = set()
        for event in reversed(events):
            if str(event['id']) in canceled:
                continue
            if event.get('type') == 'UNDO':
                target = event.get('undo_of') or event.get('payload', {}).get('eventId')
                if target is not None:
                    canceled.add(str(target))
        latest, history = {}, []
        gender_changes = [event_order(e) for e in events if e.get('type') == 'IDENTITY'
                          and 'gender' in e.get('payload', {}).get('changes', {}) and str(e['id']) not in canceled]
        for event in events:
            payload = event.get('payload') or {}
            chip = payload.get('chip')
            if event.get('type') not in ('CHIP_ON', 'CHIP_OFF') or chip not in BODY_CHIPS:
                continue
            points = (project_body(payload.get('body')) or {}).get('points', [])
            # The old event does not identify its template. A subsequent gender correction
            # can change the source UI image; avoid silently interpreting it on another image.
            template_changed = any(n > event_order(event) for n in gender_changes)
            locations = [] if template_changed else [locate(person.get('gender'), p) for p in points]
            item = dict(chip=chip, event_id=str(event['id']), type=event['type'],
                        server_at=event.get('server_at'), locations=locations,
                        status='template_uncertain' if template_changed else 'located' if locations else 'unrecorded',
                        canceled=str(event['id']) in canceled)
            history.append(item)
            if item['canceled']:
                continue
            if event['type'] == 'CHIP_OFF':
                latest.pop(chip, None)
            else:
                latest[chip] = item  # An unmarked update must clear the previous coordinates.
        state = states.get(pid)
        current = []
        for chip in (state or {}).get('chips', []) or []:
            if chip not in BODY_CHIPS:
                continue
            item = latest.get(chip)
            current.append(item or dict(chip=chip, event_id=None, locations=[], status='unrecorded'))
        if current or history:
            result[pid] = dict(current=current, history=list(reversed(history[-8:])),
                               history_omitted=max(0, len(history)-8), state_available=state is not None)
    return result


def compact_injuries(value):
    """Keep readable locations/provenance for models; raw coordinates remain in source."""
    def compact(item):
        locations = []
        seen = set()
        for loc in item['locations']:
            key = (loc['label'], loc['status'])
            if key not in seen:
                locations.append({'label': loc['label'], 'status': loc['status']})
                seen.add(key)
        return {**{k: v for k, v in item.items() if k != 'locations'}, 'locations': locations}
    return {**value, 'current': [compact(i) for i in value['current']],
            'history': [compact(i) for i in value['history']]}
