# 링크온 DB 스키마와 해온 API의 연결 분석

> 2026-09-28. 사용자 제공 참고자료를 바탕으로 한 **설계 제안**이다. 링크온 DB·서버 코드에 접속하거나 변경하지 않았다. DB 필드의 존재를 외부 API 제공·권한 부여·실시간 수신 가능의 증거로 취급하지 않는다.

## 1. 자료와 적용 범위

원본: [17-db-schema.md](/Users/enterp/Downloads/17-db-schema.md). 제공 문서의 표기는 PostgreSQL 16, 33개 표, 25개 enum, 409개 칸이다. 실제 DB와의 대조는 이번에 실행하지 않았다.

확인한 원본 SHA-256: `8aea45ecbcee60e86674b143f5c81d317aa719a893598a7fece3c8546bb3ac16`.

문서의 재생성 명령·DB 운영 지침은 참고자료의 설명으로 읽었다. 원본은 수정하지 않았고 명령도 실행하지 않았다. 여기에 기록한 필드 대응만 해온의 계획에 반영한다.

## 2. 사건을 연결하는 기준

**제안: 링크온 `room.id` → 해온 API `incident_id` → 해온 내부 session_id.**

- `room.id`: UUID 기본키. 사건 연결·수신·요약 조회에 같은 값을 사용한다.
- `room.case_no`: 사람이 읽는 고유 사건번호. 표시·검색용 보조값으로 남기고 UUID와 혼용하지 않는다.
- `room.name`: 링크온의 표시 제목. 수신 보고의 incident_title에 대응한다. 해온 조회 응답 incident_title은 해온의 세션 제목이므로 두 제목이 항상 같지는 않다.
- `room_session.id`: 사용자의 상황방 참여 기록 ID이며 사건 ID가 아니다. auth_session/duty_session ID도 사용하지 않는다.
- `account.id`: 기관·세력 계정의 ID로 프로젝트 인증 토큰이나 사건 ID와 다르다.

가상 예제에서는 `7fa6f0ba-e99b-4e2b-8be4-36ec12d4a101`을 room.id로 사용한다. 실제 링크온 값이 아니다. 기존 해온의 다른 프로젝트용 incident_id까지 UUID만 허용하도록 좁히지는 않는다. 기존 link-one 연결이 case_no를 쓰고 있다면 조용히 재연결하지 말고 시험 시 매핑을 확인한다.

링크온 서버가 해온을 조회한 뒤 사용자의 room 접근 권한을 검사해 자기 화면에 표시한다. 해온의 프로젝트 토큰은 링크온의 전체 사용자에게 각 사건 권한을 자동 부여하지 않는다.

## 3. 같은 이름처럼 보여도 구분할 값

### 실상황/훈련과 AI 실행 방식

- 링크온 `room.mode`: `REAL|DRILL`, 사고/훈련의 운영 구분이다.
- 해온 응답 `mode`: `live|demo`, 실제 모델/모의 분석의 실행 방식이다.
- **REAL=live, DRILL=demo로 변환하지 않는다.** 훈련 사건도 LIVE 모델로 분석할 수 있다.
- 1차 API는 해온 실행 mode만 제공한다. 링크온은 자신이 가진 room.mode를 별도로 유지한다. 운영 모드를 해온에 보관·돌려주는 기능은 추후 별도 필드 계약이 필요하다.

### 버전과 시각

- `room.roster_version`: 명부 판이다. 구조 상태·이송·경사·상황 종결까지 포괄하는 사건 버전이 아니다.
- `person_state.last_event_id`: 해당 사람의 상태 투영 기준 이벤트다. 전체 사건 데이터의 revision으로 쓰지 않는다.
- 해온 `state_version`: 해온 장부 버전이다. 링크온 명부 판과 숫자가 같아도 의미가 다르다.
- 해온 `revision`: 허용 응답 내용의 해시다. 링크온 DB 이벤트 순번이 아니다.
- `person_event.server_at`: 서버 기록 시각, `client_at`: 단말 시각, `offline`/`clock_skew_ms`: 지연·시계차의 맥락이다. `hull_tilt.measured_at`, `room.occurred_at`도 별도 의미를 가진다.
- 외부 데이터 확장 시 관측/단말 시각·서버 기록 시각·해온 수신 시각을 분리한다. 늦게 수신됐다는 이유만으로 최신 현장 상태로 덮어쓰지 않는다.
- bigint ID(`person_event.id`, `undo_of`, `last_event_id` 등)는 JSON에서 **10진 문자열**로 전송하는 규칙을 제안한다. UUID도 문자열이다.

## 4. 해온이 받을 현장 정보의 후보

### 사건 개요

출처는 room의 id, case_no, name, ship_name, ship_type, incident_type, waters, occurred_at, status, mode다. waters는 해역 설명 문자열이며 좌표가 아니다. 현재 5개 필드 수신에서는 room.id/name을 메타데이터로 쓰고 나머지는 보고 본문에 명시한다.

### 인원과 구조 상태

출처는 room.expected_count/roster_total/roster_version, person, person_state다. expected_count는 선사 신고, roster_total은 명부 관련 수량이므로 곧바로 해온 total에 하나를 선택해 덮어쓰지 않는다.

person_state.rescue는 UNRESCUED / RESCUED_ON_SHIP / RESCUED_OFF_SHIP으로 나뉜다. 처음에는 세 개의 원래 집계와 집계 기준을 함께 보내는 편이 명확하다. 해온의 rescued로 합치는 기준은 링크온의 기존 집계 함수·도메인 규칙을 확인한 뒤 확정한다. 선내 구조 완료와 선외 구조 완료를 임의로 같은 의미로 설명하지 않는다.

집계에서는 person의 merged_into_id, roster_excluded_at, not_boarded_at, removed_at과 명부 외 인원 처리 기준을 확인해야 한다. 단순 person 행 수나 RESCUE 이벤트 수를 총원/구조 인원으로 세지 않는다. 명부 미확보의 null은 0이 아니다. 해온은 링크온이 계산한 집계와 그 정의를 받아 검토하고, 독자적인 SQL로 링크온 상태를 재구성하지 않는 방향을 제안한다.

### 이송·관리·중증도·위치

- transit(NONE/IN_TRANSIT/RECEIVED), management(MANAGED/ENDED), rescue는 서로 다른 축이다. 인수 완료를 신규 구조로 더하지 않는다.
- location_kind는 UNKNOWN/SHIP/FORCE/IN_TRANSIT/CLOSURE다. 이송 중인 사람을 출발 세력과 도착 세력 양쪽에 동시에 세지 않는다.
- severity는 URGENT/EMERGENT/NON_URGENT/DELAYED/HOLD 또는 null이다. 별도 사망 분류로 치환하지 않는다. 코드별 의미/표시 문구는 링크온 정의를 사용한다.
- transfer의 assigned_at은 지정, received_at은 인수 확인이다. rejected_at/released_at/closed_at도 별도 상태다.
- transport_order의 SENT/ACK/DONE/REFUSED는 지시의 상태다. 해온의 recommendation을 이 테이블의 실행 지시로 자동 변환하지 않는다.

### 좌표와 선체 경사

- 제공된 room에는 위도·경도 컬럼이 없다. person_event RESCUE payload에는 선택 gps.lat/gps.lng가 있다.
- 구조 지점 좌표를 사건 전체의 현재 좌표로 간주하지 않는다. 추후 위치 타입·대상·시각·출처를 포함하고 경도 필드 lng→lon 변환을 명시한다.
- hull_tilt.roll/trim은 도 단위이며 roll 양수는 우현, trim 양수는 선수 들림이라는 문서 설명을 보존한다. measured_at과 함께 받아야 한다. 이 값으로 검증되지 않은 전복 확률을 만들지 않는다.

### 정정·취소

person_event의 UNDO/undo_of, ROSTER_MATCH/ROSTER_UNMATCH, transfer의 종결 취소 필드가 있다. 한 번 받은 숫자를 누적 증가시키는 모델로는 맞지 않는다. 기존 원문과 취소 관계를 보존한 새 보고 또는 버전 있는 집계를 받는 방식이 필요하다.

제공 문서에는 RoomStatus.CLOSED 설명의 “되돌릴 수 없다”와 RoomClosureAction.REOPEN의 “재개”가 함께 있다. 현재 코드의 실제 재개 동작은 스키마만으로 확정하지 않는다. 요약 조회는 이를 자동 종결/재개 명령으로 해석하지 않는다.

## 5. 현재 수신 계약에 연결하는 방법

현재 submit_field_report에는 다음 변환만 필요하다.

- `incident_id`: room.id의 UUID 문자열.
- `incident_title`: room.name.
- `report_id`: 링크온이 발급해 저장한 외부 보고 ID. 개별 이벤트를 보낼 경우 `person-event:<십진 ID>` 같은 접두사를 사용해 다른 테이블 ID와 충돌하지 않게 한다. 집계 보고는 집계용 독립 ID가 필요하다.
- `reported_at`: 보고 발행 시각. 오프라인 자료의 실제 처리/서버 기록 시각이 다르면 content에서 별도로 설명한다.
- `content`: 링크온 서버가 만든 6,000자 이내 현장 요약. 출처·집계 기준·자료 기준시각·미확인을 포함한다.

이 경로는 텍스트 보고 인용으로 사용할 수 있다. JSON을 content 문자열에 넣는 것만으로 구조화 인원·좌표 자동 반영 기능이 생기지는 않는다. 같은 report_id 재시도는 동일 원문이어야 하며 정정은 새 report_id를 사용한다.

1차로 받을 정보는 사건 개요, 구조 상태별 집계, 이송 진행 요약이다. 상세 환자·개별 사람·사진·음성·도면 전송은 별도 필요와 권한을 확인한 뒤 확장한다. 비밀번호/토큰 해시, QR secret, 다운로드 토큰, 바이너리 원본은 일반 상황 교환 필드에 넣지 않는다.

## 6. 링크온이 해온 요약을 받을 때

링크온은 선택한 room.id로 GET을 호출하고 현재 방의 화면에 JSON을 표시한다. 해온의 summary는 **방 전체의 분석**이다. 제공 스키마의 person_event.AI_ADVICE/AI_QA는 person_id가 있는 개인별 이벤트이므로, 사건 요약을 임의의 한 사람 이벤트에 저장하지 않는다.

현재 제공 스키마에서는 사건 전체 해온 요약을 저장할 전용 컬럼/테이블을 확인하지 못했다. 1차는 조회 후 화면 표시만 해도 된다. 영속 저장이 필요하면 링크온 측에서 별도 연동 캐시를 설계한다. 후보는 room_id, source=haeon, revision, payload(JSONB), fetched_at이며 사용자 접근은 기존 room 권한을 따른다. 이는 기존 테이블이 아니라 후속 제안이다.

## 7. 구현계획에 반영한 시험

- 링크온 room UUID로 연결/조회·수신이 같은 사건을 가리킨다. case_no/room_session ID를 섞으면 자동 매칭하지 않는다.
- room.mode=DRILL이어도 해온 mode=live를 허용하며, API가 두 의미를 치환하지 않는다.
- roster_total=null, 구조의 세 가지 값, 이동 재인수, 인물 병합/제외/취소는 후속 구조화 수신의 계약 시험 대상이다. 1차 조회 API의 구현 완료에 포함시키지 않는다.
- 1차는 해온 기록값을 투영하는 시험이며 링크온 집계 알고리즘의 정확성을 검증했다고 표시하지 않는다.
- 실제 연결 전에 링크온이 사용하는 집계 함수 결과 예제와 현장 보고 발행 방식을 확인한다. DB 스키마만으로 API 경로·인증·푸시 지원을 추측하지 않는다.

[상황 요약 계약](../../superpowers/specs/2026-09-28-linkone-summary-api.md) · [구현계획](../../superpowers/plans/2026-09-28-linkone-summary-api.md) · [JSON 예제](README.md)
