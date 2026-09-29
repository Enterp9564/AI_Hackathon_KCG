# Link-One 환자 AI 판정: DB 계약 조사

2026-09-29. **실제 읽기 전용 DB의 메타데이터·비식별 집계로 확인한 내용**이다. 개발자가 보장한 공개 API 계약이나 해온의 구현 완료 기록이 아니다. [화면·동작 설계](../superpowers/specs/2026-09-29-linkone-patient-alerts.md).

## 확인 방법과 범위

기존 `prototype/linkone_source.py`의 고정 호스트 키 SSH 터널과 `linkone_ro` 연결을 재사용했다. PostgreSQL 읽기 전용 트랜잭션에서 테이블·칼럼·enum·인덱스 및 결과 코드 집계만 조회했다. 비밀번호·키·환자 이름·개별 진료 내용·원시 모델 입력은 출력하거나 문서에 저장하지 않았다. 외부 DB 변경은 없다.

기존 로컬 전달본 `17-db-schema.md`에는 아래 분석 테이블이 없었다. 이 문서의 현행 DB 조사와 과거 전달 문서를 구별한다.

## `public.patient_ai_analysis`

각 분석 기록의 필드:

- 식별: `id bigint`, `room_id uuid`, `person_id uuid`.
- 실행: `trigger AnalysisTrigger`, `attempt integer`, `status AnalysisStatus`.
- 기준: `based_on_event_id bigint`, `based_on_at timestamptz`.
- 시간: `started_at`, `finished_at`은 timestamptz, `duration_ms integer`.
- 판정: `outcomes text[]`, `urgency text`, `summary text`, `pre_ktas jsonb`, `reasons jsonb`, `missing text[]`. 모두 nullable이다.
- 운영 필드: `requested_by_account`, `requested_by_operator`, `provider`, `model`, `prompt_version`, `sent jsonb`, `error text`.

수신 허용 대상은 식별·실행·기준·시간·판정이다. 운영 필드, 특히 `sent`와 내부 `error`는 알림 표시와 인용에 필요하지 않으므로 가져오지 않는 방향이다. 현재 앱의 일반 Link-One 전체 수신 허용 목록에도 이 테이블은 없다.

확인한 enum 전체:

- `AnalysisTrigger`: `AUTO`, `RETRY`, `MANUAL`.
- `AnalysisStatus`: `OK`, `FAILED`.
- 기존 환자 상태 `Severity`: `URGENT`, `EMERGENT`, `NON_URGENT`, `DELAYED`, `HOLD`.

`patient_ai_analysis.urgency`는 **text**이며 기존 `Severity` enum과 다른 필드다. 서로 변환하는 규칙을 임의로 만들지 않는다.

## 실제 관측값과 JSON 형태

조사 시점 전체 분석 집계에서 7개 결과가 관측됐다. 모두 `AUTO`·`OK`, 긴급도는 `IMMEDIATE` 5개와 `WITHIN_30` 2개였다. 이는 당시 표본이며 전체 허용값·주기·미래 데이터의 보장이 아니다. 기존 연결 시험 사건의 분석 결과는 0개였다.

- 관측된 outcomes: `VESSEL_TRANSFER`, `INSUFFICIENT`, `RECHECK`, `RETRIAGE`, `HOSPITAL_TRANSFER`.
- `pre_ktas`: JSON object. 관측된 키는 `criterion`, `grade`, `source`, `state`.
- `reasons`: JSON array of objects. 관측된 항목 키는 `criterion`, `record`, `text`.
- 중첩 값의 형식·공식 한국어 번역·완전한 enum은 미확인이다. 검증되지 않은 코드에 일반/정상 값을 대입하지 않는다.
- `OK`가 임상 검증 통과를 뜻한다거나 `WITHIN_30`이 현 시점부터 계산할 처치 타이머라는 해석은 확인되지 않았다.

## 확인한 인덱스

- 기본키: `(id)`.
- `patient_ai_analysis_person_id_id_idx`: `(person_id, id)`.
- `patient_ai_analysis_room_id_finished_at_idx`: `(room_id, finished_at)`.

기본키 외에 사건·환자·시도 조합의 유일성을 보장하는 인덱스는 이번 조회에서 확인되지 않았다. 재시도와 이전 분석은 별도 ID를 가질 수 있는 것으로 설계하되, ID 증가가 언제나 완료 시각 순서임을 가정하지 않는다. 최신 정렬은 완료 시각과 ID를 함께 사용하고 데이터 계약 확인 후 고정한다.

## 다른 테이블과의 구별

- `person_state.last_event_id`, `updated_at`은 판정 기준과 현재 기록을 비교할 후보 필드다. 다른 사건의 person을 결합하지 않는다.
- `anomaly_alert`는 기존 전달 문서상 현장 계정의 상세 열람 과다 등 접근 이상을 기록하는 테이블이다. 환자 응급 알림으로 사용하지 않는다.
- `hull_tilt_alert`와 `hull_tilt_alert_ack`는 선체 경사 알림·확인 이력이다. 이번 환자 알림 첫 구현의 데이터 원본으로 섞지 않는다.

## 확인되지 않은 계약

- 3분 자동 분석 스케줄/새로고침의 실제 위치와 실행 조건.
- urgency/outcomes/pre_ktas의 전체 값과 표시 의미.
- 분석 결과의 수정·삭제·유지 기간, 재시도와 최신 분석 선정 규칙.
- 병합·명부 제외·미탑승·종결 환자의 알림 포함 규칙.
- 환자 경보의 해제·해결 기준 또는 전용 환자 알림 acknowledge 필드.

위 항목은 추후 링크온 개발자 자료로 보강한다. 현재 증거로는 ‘분석 결과를 주기적으로 읽어 보여주기’가 가능하며, 별도의 의료 경보 판정기를 완성한 상태가 아니다.
