# Link-One 선체경사 경고 수신 계약

2026-09-29 실제 읽기 전용 DB 메타데이터와 제한 조회로 확인했다. 개발팀의 고정 API 보장과는 구별한다. [구현·검증](../implementation/29-alert-sorting-vessel.md).

## 허용 원문

`public.hull_tilt_alert`에서 다음 필드만 조회한다.

- 식별: `id bigint`, `room_id uuid`, `hull_tilt_id bigint`. 전달 시 문자열로 정규화한다.
- 종류: `kind HullTiltAlertKind` = `LEVEL`(각도 도달), `RAPID`(급변), `STALE`(측정 지연).
- 축: `axis TiltAxis` = `ROLL`(좌우), `TRIM`(앞뒤).
- 각도: `level_deg`, `roll`, `trim`, `prev_roll`, `prev_trim`은 double precision이다. 임의 임계값·위험도 변환을 추가하지 않는다.
- 시간: `measured_at`, `prev_measured_at`, `raised_at`은 timestamptz다. 발생 시각은 필수, 나머지 결측은 유지한다.
- 설명: `title`, `message`, `basis`, `note`, `standard`는 원문 text다. HTML로 실행하지 않고 이스케이프해 표시한다.

`public.hull_tilt_alert_ack`는 `alert_id`별 `count(*) AS ack_count`, `max(acked_at) AS last_acked_at`만 합친다. 계정 ID/이름·근무자·근무 세션은 가져오지 않는다. 경고별 확인자 수이며 해온 열람 수가 아니다.

알 수 없는 enum 문자열은 삭제/추정하지 않고 출처 값으로 표시한다. 사건 불일치·중복 ID·잘못된 시각·비유한 각도·잘못된 확인 집계·용량 초과는 해당 선박 묶음 수신을 거절하고 마지막 정상 기록을 유지한다.

## 조회와 의미

`(room_id, raised_at)` 인덱스로 사건별 최신 경고를 제한 조회하고 `(alert_id, account_id)` 유일 인덱스를 이용해 확인 집계를 읽는다. 3초 워커, 지문 비교, 최근 100건 보존과 초과 표시의 상세는 구현 문서를 따른다.

검사한 경고 테이블에는 위험 해소/종료 필드가 없다. 따라서 목록은 **선체경사 경고 기록**이며 미해소 위험의 확정 목록이 아니다. `ack_count>0`은 출처에서 누군가 확인했다는 뜻이다. 현재 Link-One 로그인 계정이 확인했다는 뜻도 아니다. 해온 열람은 해온의 판본별 읽음만 변경한다.

새로운 경고가 발행되거나 원문/확인 집계가 바뀌면 새 판본으로 보관하고 다시 알린다. 같은 판본은 중복 생성하지 않는다. 연결 해제/사건 변경 시 이전 사건 경고를 현재 사건에 노출하지 않는다. 원격 DB 쓰기·Link-One 확인 API·AI 호출은 수신 계약에 포함하지 않는다.
