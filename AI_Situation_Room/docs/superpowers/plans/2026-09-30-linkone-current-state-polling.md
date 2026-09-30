# Link-One 알림 2초·현재 상태 3초 고정 수신 Implementation Plan

> 실행 상태: 2026-09-30 후속 승인으로 구현·8860 적용 완료. 아래는 작성 당시 계획이며 실제 검증·차이는 [수신 구현](../../implementation/35-linkone-current-state.md) 및 [검증 설정 구현](../../implementation/36-critic-toggle.md)을 따른다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 사용자 요청은 현재 계획 작성에 한정되며 구현은 시작하지 않는다. 개발 보조 에이전트 생성 승인이 아니다.

**Goal:** 환자·선체 알림을 2초, 연결 사건의 현재 상태·명부·현장기록을 3초 고정 주기로 수신하며 AI를 자동 실행하지 않는다.

**Architecture:** 독립 읽기 전용 워커→세션별 현재 상태 캐시→로컬 API→현재 상황/명부 표시. 기존 분석용 전체 수신본·실행 중 문맥은 유지하고 변경 상태를 표시한다. 응급 알림 워커의 연결·오류 상태와 분리한다.

**Tech Stack:** 기존 Python HTTP·SQLite·psycopg·SSH·HTML/CSS/JavaScript, 신규 프레임워크 없음.

**Spec:** [가능성·지연 조사·수신/표시 계약](../specs/2026-09-30-linkone-current-state-polling-design.md)

## Global Constraints

- 계획 상태: 미구현·시험 미실행. 이번에 수정하는 것은 문서뿐이다.
- 정상 주기: 알림 2초, 현재 상태 3초 고정. 현재 상태 운영 옵션은 0(꺼짐)/3초. AI 호출과 원격 쓰기 0회.
- session.facts/version·분석 수신본·기존 메시지·보고·정정 이력 보존.
- 서버당 현재 상태 워커 1개(기존 알림 워커와 별도), 최대 32개 연결 사건, 응답 전체 2,000명/2,000최근기록/2MB.
- 응급 알림 연결은 독립 유지하며 기존 3초를 2초로 변경. 종결·제외·재수신·읽음 표시의 기존 의미 유지.
- 새 현재 상태를 LLM에 자동 전송하지 않는다. 키/환자 원문을 진단·공개 문서에 출력하지 않는다.
- 상시 부하 측정·추가 진단 쿼리·p95 계산·자동 주기 조절·대량 벤치마크는 제외한다.

## Review Focus

1. 구조 취소·명부 삭제/병합·미탑승으로 집계가 줄어드는 경우: 단순 max(updated_at)로 누락하지 않음(Task1).
2. AI 실행 중 현재 상태 변경: 표시만 갱신되고 실행 문맥/이전 보고는 유지(Task2·3).
3. 세션 전환·재연결·삭제 뒤 늦게 도착한 응답: 사건 혼합이나 유령 세션 생성 금지(Task2·4).
4. 음성 기록 저장 지연·취소·역순 도착: 최신 판정과 구분하고 출처 시각/취소를 표시(Task1·4).
5. 단절·상한 초과·3초보다 느린 조회·두 해온 서버/여러 브라우저: 무중첩·마지막 정상 보존·응급 알림 독립(Task2·5).

## 변경 파일과 책임

| 파일 | 계획 책임 |
|---|---|
| prototype/patient_alerts.py, prototype/static/patient-alerts.js | 알림 정상 주기 2초, 서버 메타데이터 기반 안내, 기존 백오프 유지 |
| 신규 prototype/linkone_current_source.py | 제한된 원격 조회·지문·변경 상세·독립 워커 진입점 |
| 신규 prototype/linkone_current.py | 정규화·집계·현재 상태 캐시·변경 이력·스케줄·수신 상태 |
| prototype/linkone_alert_source.py | 영구 연결 프로세스 전송부의 worker_module 인자 추가만, 기존 기본값 유지 |
| prototype/linkone_data.py | 기존 집계 로직을 순수 함수로 추출해 현재 상태/전체 수신에서 공유 |
| prototype/server.py | 워커 생명주기·주기 옵션·읽기 전용 현재 상태 API |
| 신규 prototype/static/linkone-current.js | 현재 상태/명부 보기·최근 현장기록·갱신 표시·오래된 응답 폐기 |
| prototype/static/app.js, linkone.js, index.html, style.css | 현재 상태 표시 연결, 기존 수신본 보기 유지 |
| 신규 prototype/tests/test_linkone_current.py, test_linkone_current_http.py, test_linkone_current_ui.cjs | 아래 핵심 계약 검증 |
| 13, PROGRESS, 관련 상세 구현 문서 | 구현된 범위·검증 증거·운영/복구 절차, 당시 실패 이력 보존 |

## Task 0: 기존 환자·선체 알림 조회를 2초로 변경

**Files:** prototype/patient_alerts.py, prototype/static/patient-alerts.js, prototype/tests/test_patient_alerts.py, prototype/tests/test_patient_alerts_ui.cjs.

**Interfaces:** `INTERVAL=2`; API의 `interval_seconds=2` 및 `next_check_at`도 실제 스케줄과 일치. 브라우저의 로컬 캐시 조회는 1초 유지. 기존 소스·선체 경고 쿼리와 오류 백오프 6/12/24/48/60초 유지.

- [ ] 가짜 시계·소스로 정상 조회 시작 간격 2초, 느린 조회의 중첩·밀린 조회 연속 실행 없음, 오류 백오프 유지, 종결 알림 제거를 검증하는 테스트를 추가한다. 여러 탭의 HTTP GET으로 원격 호출이 증가하지 않는지도 확인한다.
- [ ] `python3 -m unittest prototype.tests.test_patient_alerts -v`에서 새 기대값이 실패하는 것을 확인한다.
- [ ] 정상 주기 상수·표시를 변경하고 하드코딩된 ‘3초’ 문구는 API의 주기 값으로 표시한다. 타임아웃·조회 범위·모델 호출 정책은 변경하지 않는다.
- [ ] 같은 Python 시험과 `node --test prototype/tests/test_patient_alerts_ui.cjs`를 실행해 정상/오류 간격과 알림 표시를 확인한다.

## Task 1: 수신 모델·집계·원격 조회

**Interfaces**
- `person_summary(room: dict, people: list, states: list) -> dict` in linkone_data.py: 기존 prepare의 total/rescued/unresolved/unrecorded/excluded 집계 규칙 공유.
- `normalize_current(payload: dict, room_id: str) -> dict` in linkone_current.py: 정렬한 people/states/recent_records/summary, `fingerprint`, `source_updated_at`, `records_omitted` 반환.
- `read_current_poll(conn, rooms: list[str], known: dict[str,str]) -> dict`: 사건별 `{fingerprint, checked_at, data|null, error|null}`, 무변경은 data=null.
- `CurrentStateSource.poll(rooms, known)` 및 close/shutdown: 독립 프로세스 사용. AlertSource는 worker_module 기본값을 기존 모듈로 유지해 알림 호출 호환.

- [ ] 먼저 원격 테이블의 관련 인덱스·RECORD/UNDO/정정 규칙을 읽기 전용 확인하고 필드 허용목록을 명시한다. 원격 인덱스 생성은 이 계획에 포함하지 않는다.
- [ ] `test_summary_exclusion_and_rescue_undo`: 총원 3·구조 2에서 한 명 제외/구조 취소 후 기대 집계를 손으로 정한 fixture와 대조한다. 상태 없음은 위치 UNKNOWN, 명부 판본 없음은 total=None을 확인한다.
- [ ] `test_changed_record_and_deletion_change_fingerprint`: 시각이 같아도 텍스트 정정/행 제거가 지문을 바꾸고 정렬만 다르면 같음을 확인한다. 필드 외 데이터는 수신하지 않는다.
- [ ] `test_cross_room_or_partial_payload_rejected`: 사건/person 참조·중복 ID·한도 초과·누락 응답을 거부하고 음성/임의 payload가 통과하지 않는지 확인한다.
- [ ] `test_recent_records_preserve_voice_and_cancellation`: 1인 5건과 생략 개수, 원본 시각, 취소 표시, 역순 도착과 지원하지 않는 취소 연결을 검증한다.
- [ ] `python3 -m unittest prototype.tests.test_linkone_current -v`로 새 테스트 실패를 확인한 뒤 수신 모델과 조회를 구현하고 재실행한다. 전체 집계 기존 회귀도 통과시킨다.

## Task 2: 자동 수신·캐시·변경 이력

**Interfaces**
- `CurrentSituation(store, source=None, interval=3, start=True)` with start/tick/view/close.
- `view(sid: str, details=False) -> dict`: `{session_id, room_id, status, interval_seconds, checked_at, received_at, source_updated_at, fingerprint, summary, error, next_check_at}`. details=true일 때만 제한된 people/states/recent_records를 포함.
- SQLite `linkone_current_cache(session_id PK FK, room_id, fingerprint, data, received_at)`와 변경 시 불변 objects(kind=`linkone_current_snapshots`) 저장. 주기 확인/무변경의 시각은 메모리에 유지; 재시작 시 waiting 상태.

- [ ] `test_poll_changes_display_without_ai_or_session_mutation`: 연속 fixture로 구조 인원/현장기록만 바뀌는 것을 확인하고 runs/messages/version/facts/전체 수신본 개수가 바뀌지 않음을 확인한다. source.poll은 fake, 나머지 Store는 실제 임시SQLite를 쓴다.
- [ ] `test_unchanged_does_not_append_history`: 같은 지문 100회 확인해 변경 판본 1개만 저장되는지 검증한다.
- [ ] `test_reconnect_and_deleted_session_discard_inflight_result`: 수신 중 사건 변경·세션 삭제는 새 자료 적용/세션 재생성을 하지 않는다. 재연결 시 새 사건 첫 상세 수신을 강제한다.
- [ ] `test_error_backoff_and_restart_preserve_last_good`: 오류 6/12/24/48/60초, 회복 3초, 재시작 waiting, interval=0 꺼짐, 느린 호출 비중첩을 가짜 시계로 검증한다.
- [ ] 테스트 실패 확인→최소 구현→통과. 기존 PatientAlerts나 Engine.submit을 호출하지 않는지 인터페이스와 부작용으로 확인한다.

## Task 3: API·실행 중 분석 보호·운영 옵션

**Interfaces**
- 새 `GET /api/sessions/{sid}/linkone-current`: details=true인 현재 캐시, 캐시 없음도 명시된 waiting/disabled 상태. GET은 원격 수신을 즉시 실행하지 않는다.
- 기존 `/api/sessions/{sid}` 응답에 요약형 `live_situation` 추가. Engine의 Store.snapshot 입력에는 자동 합성하지 않는다.
- `--linkone-current-interval {0,3}` 기본 3; make_server에 current_source 테스트 주입 인자 추가. 기존 외부 연결을 막는 테스트 주입 규칙을 유지한다.
- `basis_matches`는 수동 수신본에서 동일 표시용 필드를 정규화한 지문과 비교해 true/false/null 반환. source/snapshot fingerprint와 알고리즘 버전을 함께 기록한다.

- [ ] `test_current_endpoint_reads_cache_without_source_fetch`: 반복 HTTP GET에도 원격 poll이나 AI 생성이 늘지 않음, Host/Origin·세션 격리·404 적용 확인.
- [ ] `test_running_analysis_keeps_original_context`: 실행 중 수신 변화에도 model에 준 문맥과 수신본은 동일하고 live_situation만 바뀜을 확인한다.
- [ ] `test_basis_comparison_handles_unknown_and_newer_manual_snapshot`: 수동 동기화 직후 오래된 캐시가 최신으로 덮어 보이지 않게 조회 시각/판본을 확인한다. 비교 불가를 true로 만들지 않는다.
- [ ] 테스트 실패→서버 연결 구현→`python3 -m unittest prototype.tests.test_linkone_current_http -v`. HTTP 포트 권한이 필요한 시험과 실제 원격 조회를 구분한다.

## Task 4: 현재 상황·명부·현장기록 표시

**Interfaces**
- `currentSituationView(snapshot)`는 표시할 요약/원천/지연 상태를 결정하는 순수JS 함수.
- `renderCurrentSituation(snapshot)`, `openCurrentRoster(sid)`, `resetCurrentSituation()` in linkone-current.js.
- 로컬 전체 화면 1초 조회에서 요약을 받고, 열려 있는 현재 명부만 1초 간격으로 상세 API 조회. 서버 원격 주기는 브라우저 수와 독립.

- [ ] `test_current_counts_and_stale_source_label`: 최신 집계가 우선 표시되며 오류/10초 지연/재시작 waiting 시 마지막 정상 자료와 시각을 유지한다. 최초 캐시 없음은 수동 수신본임을 표시한다.
- [ ] `test_roster_refresh_preserves_user_state`: 검색·컬럼 정렬·스크롤·펼친 행·과거판본 선택·작성 중 채팅 초안을 유지한다. 명부 전환/모달 닫기 뒤의 늦은 응답은 버린다.
- [ ] `test_voice_record_renders_before_ai_alert`: 신규 RECORD가 있어도 환자 AI 판정이 이전인 fixture에서 현장기록은 먼저 표시하고 판정 완료를 꾸며내지 않는다. 기록 텍스트는 HTML escape한다.
- [ ] `test_new_state_does_not_mark_old_report_current`: 수신본과 차이를 알리고 기존 보고 내용/실행 상태를 수정하지 않는다.
- [ ] 실패→화면 연결 구현→`node --test prototype/tests/test_linkone_current_ui.cjs`; 이후 임시DB 브라우저에서 숫자 변화/명부/음성 표시/초안 보존을 확인한다. 운영 데이터 변경으로 시험하지 않는다.

## Task 5: 최소 기능 검증·단계적 적용

- [ ] 가짜 시계와 제한된 훈련 fixture로 알림 2초·현재 상태 3초 스케줄, 무변경 저장 생략, 여러 탭/같은 사건 중복 제거, 두 서버의 독립 워커, 상한 초과·단절·회복을 검증한다. 실제 대량 요청을 발생시키는 부하 시험은 넣지 않는다.
- [ ] 임시 DB·브라우저에서 구조 인원 변경과 음성 RECORD가 AI 판정 이전에 표시되는지 확인한다. 운영 DB 쓰기 없이 source fixture를 바꿔 시험한다. 조회 주기를 음성 입력부터 표시까지의 보장 시간으로 보고하지 않는다.
- [ ] `python3 -m unittest discover -s prototype/tests -q`, `node --test prototype/tests/test_*.cjs`, JS 문법, `git diff --check`. 수신 기능만으로 LLM 호출이 발생하지 않음을 확인한다.
- [ ] 상시 측정 스레드, 진단 SQL, p95 계산, 자동 주기 전환이 추가되지 않았는지 변경 코드를 검토한다. 기존 시각/오류 기록과 마지막 확인 시각은 유지한다.
- [ ] 적용 단계에서는 운영 유휴를 확인하고 한 서버씩 변경한다. 기존 세션 수·모델·SAR 설정과 알림 수신을 확인한다. 이번 계획 작성 단계에서는 재시작하지 않는다.
- [ ] 문제 발생 시 현재 상태 수신은 옵션 0으로 중지하고, 알림 주기 변경은 해당 코드 변경만 되돌린다. 기존 캐시·변경 이력·수신본은 보존한다. 5초 자동 조절은 하지 않는다.
- [ ] 구현 결과는 13·PROGRESS·관련 상세 구현 문서에 실제 수행한 검증 종류별로 기록한다. 이번 요청으로 커밋·푸시를 실행하지 않는다.

## 완료 판단

**계획 완료와 기능 완료를 구별한다.** 기능 완료는 조회/화면의 신규 변경 반영, 기록 취소/정정, 기존 분석 문맥 보존, 원격/LLM 쓰기 0, 장애 복구, 고정 주기와 무중첩 계약을 실행 증거로 확인한 상태다. 현재는 읽기 전용 지연 조사와 설계/작업계획만 완료했으며 코드·DB·설정은 변경하지 않았다.

## 관련 기능

[검증요원 ON/OFF 구현 계획](2026-09-30-critic-toggle.md)은 독립적으로 적용할 수 있다. 수신 주기를 바꾸거나 알림을 받는 행위가 검증요원 설정이나 AI 실행을 바꾸지는 않는다.
