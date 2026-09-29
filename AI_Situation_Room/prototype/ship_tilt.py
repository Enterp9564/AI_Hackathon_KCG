"""Measurement arithmetic only; design references are not a capsize classifier."""
import math
import time
from datetime import datetime

REFERENCES = {
    'roll': ((7, 'damage_equilibrium_7'), (10, 'passenger_intact_10'),
             (15, 'damage_equilibrium_15'), (15, 'machinery_static_list_15'),
             (20, 'launching_list_20'), (22.5, 'machinery_dynamic_roll_22_5'),
             (22.5, 'emergency_power_list_22_5')),
    'trim': ((7.5, 'machinery_dynamic_pitch_7_5'), (10, 'launching_trim_10'),
             (10, 'emergency_power_trim_10')),
}


def angle(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and abs(value) <= 180 else None


def assess_tilt(rows, now=None):
    now = time.time() if now is None else now
    samples = []
    excluded = 0
    partial = 0
    for row in rows:
        try:
            stamp = datetime.fromisoformat(row['measured_at'].replace('Z', '+00:00'))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError('timezone missing')
            timestamp = stamp.timestamp()
            if timestamp > now:
                raise ValueError('future measurement')
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            excluded += 1
            continue
        values = {axis: angle(row.get(axis)) for axis in REFERENCES}
        if all(value is None for value in values.values()):
            excluded += 1
            continue
        partial += any(value is None for value in values.values())
        samples.append((timestamp, dict(id=row.get('id'), measured_at=stamp.isoformat(), **values)))
    samples.sort(key=lambda item: item[0])
    result = dict(measurement_source=dict(type='field_instrument', basis='user_confirmed_linkone_workflow',
                  note='사용자가 확인한 링크온 현장 계측 장비 실측 경로. 유효 수신값을 판단 근거로 사용. 개별 장비의 교정 인증을 해온이 수행했다는 뜻은 아님.'),
                  evaluated_at=now, source_rows=len(rows), usable_rows=len(samples),
                  excluded_rows=excluded, partial_rows=partial, latest=None, age_seconds=None,
                  latest_time_ambiguous=False, change=None, numeric_reference_matches={'roll': [], 'trim': []},
                  operational_alarm_thresholds=None,
                  interpretation='수신본 내 유효 측정의 수치 비교. 설계 조건 충족·위반이나 전복 위험 등급이 아님. 제외/불완전 측정이 있으면 최신성·추세가 불확실함. ship_tilt_guidance의 적용 조건과 함께 사용.')
    if not samples:
        return result
    timestamp, latest = samples[-1]
    ambiguous = len(samples) > 1 and samples[-2][0] == timestamp
    result['latest_time_ambiguous'] = ambiguous
    result['age_seconds'] = round(now-timestamp, 1)
    # Simultaneous records have no documented tie-breaker; do not choose one as fact.
    if ambiguous:
        return result
    latest['roll_direction'] = None if latest['roll'] is None else ('우현' if latest['roll'] > 0 else '좌현' if latest['roll'] < 0 else '수평')
    latest['trim_direction'] = None if latest['trim'] is None else ('선수 들림' if latest['trim'] > 0 else '선수 내려감' if latest['trim'] < 0 else '수평')
    result['latest'] = latest
    for axis, references in REFERENCES.items():
        if latest[axis] is not None:
            result['numeric_reference_matches'][axis] = [key for value, key in references if abs(latest[axis]) >= value]
    if len(samples) < 2 or (len(samples) > 2 and samples[-3][0] == samples[-2][0]):
        return result
    previous_time, previous = samples[-2]
    elapsed = timestamp-previous_time
    change = dict(from_id=previous['id'], from_measured_at=previous['measured_at'], elapsed_seconds=elapsed)
    for axis in REFERENCES:
        before, after = previous[axis], latest[axis]
        change[axis] = None if before is None or after is None else dict(
            from_deg=before, to_deg=after, signed_delta_deg=round(after-before, 6),
            magnitude_delta_deg=round(abs(after)-abs(before), 6),
            average_magnitude_deg_per_min=round((abs(after)-abs(before))*60/elapsed, 6),
            direction_crossed=before*after < 0)
    result['change'] = change
    return result
