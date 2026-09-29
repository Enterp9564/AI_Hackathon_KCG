# 링크온 사건별 상황 요약 JSON API 구현계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 개발 보조 에이전트 생성은 이 계획의 요구가 아니다.

**Goal:** 링크온이 사건 ID로 해온의 현재 장부·상황 요약·분석 상태를 JSON으로 조회하게 한다.

**Architecture:** 기존 외부 MCP listener에 일반 HTTP GET 경로를 추가하고, 별도 ExportService가 프로젝트별 사건 공유와 일관된 DB 읽기를 담당한다. 허용 필드만 투영해 JSON을 만들며 조회로 AI를 실행하지 않는다. MCP 조회 호환은 REST 완료 뒤 같은 서비스를 재사용한다.

**Tech Stack:** 기존 Python 표준 HTTP 서버·SQLite·HTML/CSS/JavaScript. 새 웹 프레임워크·모델·패키지 의존성 없음.

**Spec:** [분석·통신 계약](../specs/2026-09-28-linkone-summary-api.md). 사용자 확정: **링크온이 필요할 때 해온 API를 조회**. 세부 필드·구현 순서는 검토용 제안이며 아직 구현하지 않았다.

**Reference:** [사용자 제공 링크온 DB 스키마 대응](../../contracts/linkone-summary-v1/linkone-db-mapping.md). 링크온 room.id를 사건 ID로 쓰는 안을 반영한다. DB 스키마는 실제 API나 링크온 집계 함수의 구현 증거가 아니다.

## Global Constraints

- 임시 명칭은 HAEON(해온), 해양경찰 멀티에이전트 의사결정 지원 시스템이다.
- Python HTTP·SQLite·HTML/CSS/JavaScript를 유지한다. 모델 설정은 gpt-6-luna, 모든 역할 medium이며 이번 작업에서 바꾸지 않는다.
- 로컬 `/api/*`를 외부에 공개하지 않는다. 기존 외부 listener에 `/integration/v1/situation-summary`를 추가한다.
- 프로젝트별 토큰과 `(project,incident_id)` 연결을 사용한다. 공유 설정은 기본 꺼짐이다.
- GET은 장부·run·수신함·모델 호출 수를 바꾸지 않는다.
- 상태 current는 장부 버전 일치만 뜻한다. simulation을 현재 상황 요약으로 내보내지 않는다.
- 링크온 room.mode(REAL/DRILL)와 해온 mode(live/demo)는 별도 의미다. person_state의 구조/이송/관리 상태나 roster_version을 임의 변환하지 않는다.
- 기존 MCP 현장 보고의 5개 필드·원문·정정·중복 방지·인용 승인 동작을 보존한다.
- 조회 성공과 AI 완료·사실 확정·실제 출동을 구분한다. LIVE/DEMO와 불확실성을 보존한다.
- 키·환경변수 값은 출력하거나 문서/커밋에 넣지 않는다. `.secrets/`, `runtime/` 원본은 삭제하거나 시험에 사용하지 않는다.
- 단위·HTTP·브라우저·팀 앱·LIVE 검증 결과를 나눠 기록한다. 아래 예상 결과는 아직 실행한 결과가 아니다.

## Review Focus

1. 장부 version이 같아도 새 final이 생기면 revision이 바뀌어야 한다 → 작업 2.
2. snapshot 읽기 중 장부 수정·공유 해제가 발생해 다른 시점의 자료가 섞이지 않아야 한다 → 작업 1·3.
3. 다른 프로젝트의 동일 사건 ID·삭제된 연결을 통해 정보가 노출되지 않아야 한다 → 작업 1·3.
4. 최신 분석이 실패하거나 simulation이 최신이어도 이전 유효 analysis와 현재 처리 상태를 구분해야 한다 → 작업 2.
5. 한글/슬래시 사건 ID·null 인원·늦은 응답·요약 안의 외부 주장을 소비자가 잘못 해석하지 않아야 한다 → 작업 2·3·5.

---

## 1. 구현 파일과 책임

- 신규 `prototype/exports.py`: 공유 테이블, 공유 설정, 인증된 사건 읽기, JSON 투영, revision 계산. 전송 방식과 무관한 서비스다.
- 수정 `prototype/mcp_server.py`: 공통 Host/Origin/Bearer 검사와 경로별 처리, REST 조회. 후속 MCP 조회 도구도 이곳에서 연결한다.
- 수정 `prototype/server.py`: 서비스 초기화, 로컬 공유 설정 API, 로컬 inbox 응답의 공유 상태.
- 수정 `prototype/static/inbox.js`, `prototype/static/index.html`, 필요 시 `prototype/static/style.css`: 연결 사건별 공유 설정 표시와 조작.
- 신규 `prototype/tests/test_exports.py`: DB 격리·공유 설정·보고 투영·변경 판정·읽기 동시성.
- 신규 `prototype/tests/test_summary_http.py`: 외부 REST 계약과 로컬 공유 API.
- 신규 `prototype/tests/browser_summary_export.cjs`: 격리 서버의 공유 설정·인용·조회 DEMO 동선.
- 수정 `prototype/tests/test_mcp.py`: 기존 수신 회귀. 후속 MCP 조회 단계에서 추가 도구를 검사한다.
- 신규 `prototype/tests/test_summary_contract.py`: JSON 예제·코드 응답 형태의 일치 및 안정성.

`store.py`, `engine.py`, 모델 프롬프트 변경은 기본 계획에 없다. ExportService는 기존 Store.db와 기존 테이블을 사용한다. 내부 helpers를 사용할 경우 호출이 동일 db 연결을 유지하게 한다. 런타임 전체 snapshot을 외부 직렬화하지 않는다.

## 2. 구현 순서

작업 1 → 2 → 3 → 4 → 5를 1차 REST 범위로 진행한다. 작업 6은 후속 MCP 조회 호환이며 링크온 REST 연결의 선행조건이 아니다. webhook·수신 v2·자동 사실 반영은 이번 작업 목록에 없다.

### 작업 1: 사건별 공유 권한과 일관된 읽기

**Files:** 신규 `prototype/exports.py`, `prototype/tests/test_exports.py`.

**Interfaces:**
- `ExportService(store: Store)` → integration_exports 테이블을 멱등 초기화한다.
- `set_shared(sid: str, project: str, incident_id: str, enabled: bool) -> dict` → 계약 §7의 설정 객체.
- `list_shares() -> list[dict]` → 로컬 담당자 전용 설정 목록. 외부에 직접 반환하지 않는다.
- `read_source(project: str, incident_id: str) -> dict` → `{session, runs, partner_pending_report_count}`. 동일 읽기 트랜잭션으로 권한과 자료를 확인한다.
- 조회 불가를 나타내는 `ExportNotAvailable(Exception)`. 입력 오류는 ValueError, 다른 세션 설정은 기존 Conflict 사용.

- [ ] **1. 실패 시험 작성:** 새 연결에서 read_source는 ExportNotAvailable, 같은 사건 공유를 켜면 성공, 끄면 실패를 검증한다. enabled=1/"true"는 ValueError여야 한다.
- [ ] **2. 격리 시험 실행:** `python3 -m unittest prototype.tests.test_exports -v`. 구현 전 import 또는 미구현 메서드 실패를 확인한다.
- [ ] **3. 공유 테이블과 서비스 구현:** 설계 §7의 복합 FK/삭제 연쇄를 적용한다. 설정 갱신은 짧은 쓰기 트랜잭션, 읽기는 명시적 BEGIN으로 일관된 시점을 고정한다. 네트워크·모델 호출은 넣지 않는다.
- [ ] **4. 경계 시험 추가:** link-one와 resaid-ai에 같은 incident_id를 다른 세션으로 연결해 서로의 장부가 나오지 않음을 확인한다. 다른 sid로 설정 요청 시 Conflict, 삭제/재생성 뒤 공유 기본 꺼짐, 재시작 뒤 기존 공유 보존을 검증한다.
- [ ] **5. 동시성 시험:** 별도 DB 연결과 barrier로 읽기 사이에 장부 수정/공유 해제를 넣는다. 반환은 수정 전 또는 후의 일관된 자료이며 권한 확인과 session이 서로 다른 시점으로 섞이지 않아야 한다. 해제 완료 후 시작한 요청은 실패해야 한다.
- [ ] **5a. 링크온 식별 시험:** 가상 room UUID로 연결/조회하고, case_no나 room_session ID로 조회했을 때 자동 추측 매칭하지 않음을 확인한다.
- [ ] **6. 동일 시험 재실행:** 작업 1의 시험이 모두 OK인 것을 확인한다. 관련 파일만 확인해 단계 커밋하고 기존 사용자 수정·runtime·비밀을 포함하지 않는다.

### 작업 2: 현재 상황 JSON과 보고 선택

**Files:** 수정 `prototype/exports.py`, `prototype/tests/test_exports.py`; 신규 `prototype/tests/test_summary_contract.py`.

**Interfaces:**
- `build_summary(project: str, incident_id: str, *, now: float | None = None) -> dict` → 설계 §5의 전체 JSON. 내부에서 read_source 호출.
- `project_summary(source: dict, incident_id: str, *, now: float) -> dict` → DB/LLM 접근 없는 투영 함수.
- `summary_revision(payload: dict) -> str` → served_at/revision을 제외한 canonical JSON의 sha256 해시.
- 최종 응답 크기 제한은 전송 계층에서 검사한다. 투영 함수는 외부 허용 키만 명시적으로 구성한다.

- [ ] **1. 실패 시험 작성:** 장부 version=3에 analysis final 기준=3이면 current, 장부만 version=4로 바꾸면 stale, final이 없으면 unavailable을 확인한다. null 인원은 0으로 바꾸지 않는다.
- [ ] **2. 실행:** `python3 -m unittest prototype.tests.test_exports prototype.tests.test_summary_contract -v`. 미구현 투영/계약 때문에 실패함을 확인한다.
- [ ] **3. 필드 매핑 구현:** facts의 6개 값(total/rescued/remaining/location/lat/lon), final의 요약/판단/권고/불확실성/질문만 제공한다. 질문은 question/reason/priority만 투영한다. 자료형·기본값·시간·고정 문자열은 설계 §5를 따른다.
- [ ] **4. 후보 선택 구현:** analysis·유효 final·completed/stale 후보를 `(created_at,id)`로 선택한다. simulation/failed/interrupted와 손상 보고는 제외한다. processing은 별도로 최신 analysis와 pending 개수를 계산한다.
- [ ] **5. 동작 시험 추가:** 최신 simulation 제외, 최신 failed에서도 이전 성공 보고 유지, 실패는 processing에 노출, 동일 version의 새 final에서 revision 변경, 시각만 변경하면 revision 동일, 외부 인용의 contains_external_claims=true를 검증한다.
- [ ] **6. 비노출 시험:** 가짜 토큰·프롬프트·명부 이름·첨부 내용·calls 값에 서로 다른 표식을 넣고 응답에 없는지 확인한다. 별도로 final.summary에 들어 있는 텍스트는 그대로 나갈 수 있음을 검사해 익명화로 오해하지 않게 한다. 다른 프로젝트 미처리 보고는 count에서 제외한다.
- [ ] **6a. mode 의미 시험:** 링크온 훈련 방과 연결한 해온 LIVE 세션의 응답은 mode=live를 유지한다. room.mode 또는 roster_version으로 해온의 mode/state_version을 덮어쓰는 경로가 없어야 한다.
- [ ] **7. JSON 계약 시험:** [예제 폴더](../../contracts/linkone-summary-v1/README.md)의 3개 응답을 fixture로 사용한다. 고정 now·session·run 입력에서 동일 JSON과 revision이 생성되는지 확인한다. 출력의 모든 키·null/array·시각 형식을 검사한다.
- [ ] **8. 같은 명령 재실행:** 작업 1·2 시험 전체 OK를 확인하고 관련 변경만 단계 커밋한다.

### 작업 3: 일반 HTTP JSON 조회 제공

**Files:** 수정 `prototype/mcp_server.py`, `prototype/server.py`; 신규 `prototype/tests/test_summary_http.py`; 기존 `prototype/tests/test_mcp.py` 회귀.

**Interfaces:**
- 기존 `make_mcp_server(inbox, tokens, host='127.0.0.1', port=8862, allowed_hosts=())` 호출 호환성을 보존한다. 내부에서 `ExportService(inbox.store)`를 사용한다.
- `GET /integration/v1/situation-summary?incident_id=...` → build_summary의 dict. POST/DELETE/PUT/PATCH/HEAD/OPTIONS는 이 REST 경로에서 405 JSON과 Allow: GET으로 일관되게 거절한다.
- MCP `/mcp`의 기존 메서드·헤더·도구 성공/오류 계약은 유지한다. MCP content-type/protocol 조건을 REST GET에 적용하지 않는다.

- [ ] **1. HTTP 실패 시험 작성:** 임시 DB·임시 토큰·port=0 서버에서 공유 사건 GET 200과 JSON, 비공유 404, 토큰 없음 401, 불허 Host/Origin 403을 확인한다.
- [ ] **2. 실행:** `python3 -m unittest prototype.tests.test_summary_http prototype.tests.test_mcp -v`. 신규 경로가 없어 실패하는 것을 확인한다.
- [ ] **3. 경로/인증 분리 구현:** 지금 access()에 묶인 `/mcp` 경로 검사를 라우팅과 분리한다. 인증 결과 project만 서비스에 전달한다. REST는 Accept가 없거나 */* 또는 application/json을 허용하고, 명시적으로 JSON을 배제하면 406 `not_acceptable`을 반환한다.
- [ ] **4. query 검사 구현:** 정확히 하나의 incident_id만 허용하고 1~120자·엄격 UTF-8/% 디코딩을 검사한다. project/session_id/중복/빈 값은 400. GET 본문으로 사건을 덮어쓰지 않는다. 본문이 있는 GET은 400이다.
- [ ] **5. 응답 구현:** 설계 §4의 오류 객체·상태 코드·no-store·UTF-8 및 262,144바이트 제한을 적용한다. HEAD 오류 응답은 HTTP 의미에 맞게 본문을 보내지 않는다. Authorization·보고 원문·traceback 로그는 남기지 않는다.
- [ ] **6. 시험 확장:** 한글·공백·슬래시 사건 ID의 URL 인코딩, 잘못된 인코딩, 다른 프로젝트 동일 ID, 다른 사건 접근, 연결 삭제, 요청 중 공유 해제, 크기 초과의 명시 오류를 검증한다.
- [ ] **7. 읽기 전용 검증:** API 연속 10회 호출 전후 sessions/objects/inbox_reports 레코드와 모델 호출 수가 동일함을 확인한다. 임시 모의 Engine은 호출 시 시험 실패하도록 한다.
- [ ] **8. 회귀 실행:** `python3 -m unittest prototype.tests.test_summary_http prototype.tests.test_exports prototype.tests.test_mcp prototype.tests.test_inbox prototype.tests.test_http -v`. 기존 수신과 일반 UI API도 OK여야 한다. 단계 커밋한다.

### 작업 4: 담당자의 사건 공유 설정

**Files:** 수정 `prototype/server.py`, `prototype/static/inbox.js`, `prototype/static/index.html`, 필요 시 `prototype/static/style.css`; 수정 `prototype/tests/test_summary_http.py`; 신규 `prototype/tests/browser_summary_export.cjs`.

**Interfaces:**
- 로컬 `POST /api/sessions/{sid}/integration-export` body `{project,incident_id,enabled}` → ExportService.set_shared 결과.
- 로컬 `GET /api/inbox` 기존 reports/links/projects 유지 + `exports` 배열 추가.
- 화면은 연결 ID별 “상황 요약 공유” 체크와 “현재·향후 요약을 이 프로젝트에 제공합니다” 설명을 제공한다. REST 상대 경로를 표시하며 비밀·토큰을 렌더링하지 않는다.

- [ ] **1. HTTP 실패 시험:** X-Session-Token 누락·다른 sid·미연결·enabled 문자열 거절, 설정 성공 후 외부 GET 허용, 끄면 404를 검증한다.
- [ ] **2. 로컬 API 구현:** 기존 로컬 Host/Origin/토큰 검사를 유지하고 외부 listener에는 이 쓰기 경로를 만들지 않는다. exports 목록은 로컬 UI 응답에서만 노출한다.
- [ ] **3. UI 구현:** 현재 선택 사건의 연결별 설정을 표시하고 저장 중 중복 조작을 막는다. 서버 성공 후 상태를 표시하며 실패 시 기존 값으로 되돌리고 오류를 보여준다. 새로고침·세션 전환 때 저장된 설정을 읽는다.
- [ ] **4. 브라우저 시험 작성/실행:** `node prototype/tests/browser_summary_export.cjs`. 기존 browser_inbox.cjs의 격리 서버/브라우저 실행 방식을 따른다. A만 공유했을 때 A 200/B 404, B로 전환 후 A 설정 오조작 방지, 공유 끄기, 키보드 접근·오류 표시를 검사한다.
- [ ] **5. 구문·HTTP 확인:** `node --check prototype/static/inbox.js`, `python3 -m unittest prototype.tests.test_summary_http -v`. 신규 시험과 기존 `node prototype/tests/test_send.cjs`가 통과해야 한다. 관련 변경만 단계 커밋한다.

### 작업 5: 계약 예제·전체 왕복·문서 인수

**Files:** 수정 `docs/contracts/linkone-summary-v1/` 예제/안내, `prototype/README.md`, `prototype/PROGRESS.md`, `13_현재상태_요구사항_인수인계.md`, `docs/implementation/13-http-api.md`, `16-external-inbox.md`, `17-mcp-transport.md`, `18-hotspot-testing.md`(이 네 파일은 모두 docs/implementation 아래), `docs/improvements/01-project-api-integration.md`.

**Interfaces:** 링크온 서버는 GET 후 JSON 파싱만 한다. 수신 현장 보고는 기존 submit_field_report 계약을 유지한다. 구현과 예제의 고정 이름/값을 작업 2 계약 시험으로 묶는다.

- [ ] **1. 왕복 DEMO 시나리오:** 임시 DB의 가상 A·B 사건을 만든다. A 연결/공유 → 링크온 모의 GET(unavailable) → MCP 현장 보고 제출(pending) → GET에서 pending 수 증가·AI 호출 없음 → 담당자 인용 → 분석 완료 → GET에서 summary와 외부 주장 표시를 확인한다. 수신/인용만으로 장부가 바뀌지 않아야 한다.
- [ ] **2. 상태 변화 시나리오:** 담당자가 facts를 수정하면 새 장부와 stale 요약이 함께 나온다. 새 analysis 완료 후 current와 새로운 revision이 나온다. 최신 simulation은 조회 결과에 섞이지 않는다. 호출/기록은 DEMO라고 명시한다.
- [ ] **3. 수신자 예제 검증:** 필요한 필드만 추출하는 일반 HTTP 클라이언트로 JSON을 읽는다. 모르는 추가 선택 키는 무시하고, null/상태를 표시하며, 사건 전환 뒤 늦은 응답은 무시한다. 토큰은 서버 환경에서만 사용한다.
- [ ] **4. 앱 검증:** `python3 -m unittest discover -s prototype/tests -q`, `node prototype/tests/test_send.cjs`, `node --check prototype/static/app.js`, `node --check prototype/static/inbox.js`, `node prototype/tests/browser_summary_export.cjs`. 실행한 결과만 단위/HTTP/브라우저로 나눠 기록한다. 실패는 원인·수정·재실행을 남긴다.
- [ ] **5. 팀 앱 검증:** 합의한 시험망·해온 IP·링크온 사건 ID·토큰 파일로 링크온 실제 서버에서 조회한다. 사건 선택, current/stale/unavailable, 인증 실패, 공유 해제, 연결 단절 후 표시를 확인한다. 상대 앱이 준비되지 않으면 `not_run`으로 남기고 로컬 성공으로 대체하지 않는다.
- [ ] **6. 문서 현행화:** 새 API를 실제 구현으로 옮겨 기록하고 기존/신규 계약을 구분한다. 포트 활성 명령·토큰 파일 전달 방식·사건 공유·링크온 GET 예제를 추가한다. LIVE는 별도 요청/시험 없으면 미실시다. 문서 링크·예제 계약 재검사 후 관련 변경만 커밋한다.

### 작업 6: 후속 MCP 조회 호환

**Files:** 수정 `prototype/mcp_server.py`, `prototype/tests/test_mcp.py`, `docs/implementation/17-mcp-transport.md`.

**Interfaces:** `get_situation_summary({incident_id: str})` → ExportService.build_summary의 JSON. 도구 arguments는 정확히 incident_id 하나, 1~120자. structuredContent와 content text의 JSON은 같은 값이다.

- [ ] **1. 실패 시험:** tools/list에서 submit_field_report와 get_situation_summary가 발견되고, 조회 도구가 REST와 같은 공유 범위/필드를 반환해야 한다. served_at을 제외한 값과 revision을 대조한다.
- [ ] **2. 구현:** 기존 단일 TOOL을 도구 목록으로 확장한다. 조회도구는 readOnlyHint=true로 표시한다. 조회 불가/입력 오류는 isError=true, 정상은 isError=false다. 내부 오류는 기존 일반화한 MCP 서버 오류를 유지한다.
- [ ] **3. 검증:** `python3 -m unittest prototype.tests.test_mcp prototype.tests.test_summary_http prototype.tests.test_inbox -v`. 도구 호출과 MCP 알림을 구분하고 알림 형태의 조회/수신이 실행되지 않음을 확인한다.
- [ ] **4. 문서·단계 커밋:** REST가 필수, MCP 조회는 선택임을 명시하고 실행한 결과만 기록한다.

## 3. 완료·중단·복구 기준

- 계획 작성 완료와 구현 완료는 다르다. 현재 체크박스는 모두 미실행이다.
- 1차 완료: 작업 1~5의 로컬 시험 통과와 계약 문서 현행화. 실제 링크온 시험이 미실시라면 “해온 측 준비 완료, 팀 앱 연동 미검증”으로 표시한다.
- MCP 조회는 작업 6을 실행했을 때만 제공한다고 기록한다. webhook/v2 수신이 구현됐다고 표시하지 않는다.
- 문제가 생기면 해당 사건의 공유를 끄거나 외부 listener를 비활성화한다. 기존 로컬 사건·수신 원문·새 공유 이력은 임의 삭제하지 않는다.
- 코드 되돌림은 앱 중지·DB 백업 후 수행하며 additive 테이블을 삭제할 필요는 없다. 토큰을 재발급해야 하면 값 출력 없이 기존 파일 취급 방식을 따른다.
- 기존 작업 트리가 다수 변경돼 있으므로 `git add .`를 사용하지 않는다. 사용자 변경과 생성물·비밀을 구분해 단계별 대상 파일만 확인한다.

## 4. 계획 자체 검토 기록

설계 §1~3 → 범위/작업 순서, §4 → 작업 3, §5~6 → 작업 1~2, §7 → 작업 1·4, §8 → 작업 5, §9 → 기존 회귀/후속 범위, §10 → 작업 6, §11 → 완료 기준으로 대응한다. 함수명·응답 키·버전·미실행 상태의 일관성을 문서 검사 대상으로 둔다. 실제 통신 주소·사건 ID·비밀 전달 경로는 팀 앱 시험 시점에 제공받는다.
