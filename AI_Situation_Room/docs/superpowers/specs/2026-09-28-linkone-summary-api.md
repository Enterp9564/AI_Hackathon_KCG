# 링크온 사건별 상황 요약 JSON API — 분석·설계안

> 2026-09-28. **검토용 설계이며 아래 신규 API는 미구현이다.** 사용자가 확정한 수신 방식은 “링크온이 필요할 때 해온 API를 조회”다. 구현계획은 [작업별 계획](../plans/2026-09-28-linkone-summary-api.md), 전달 예제는 [JSON 예제 안내](../../contracts/linkone-summary-v1/README.md)를 따른다.

## 1. 사용자 요구와 설계 범위

- 해온은 사건별 현재 상황 요약을 링크온에 제공한다.
- 링크온은 필요한 시점에 HTTP로 조회하고 JSON에서 필요한 항목을 선택해 사용한다.
- 링크온의 현장 보고는 기존 MCP 수신함으로 받는다. 담당자 인용 승인 후 기존 분석으로 연결한다.
- 나중에 수신·송신 데이터가 늘어도 기존 연동이 깨지지 않게 확장 규칙을 정한다.
- 이번 산출물은 분석, 통신 계약 초안, 구현계획, 가상 JSON 예제다. 서버 공개·기능 구현·실제 팀 앱 연동을 이번 완료로 주장하지 않는다.

“자유롭게 수신”은 언어·프레임워크·화면 구성이 자유롭고 필드를 선택해 활용할 수 있다는 의미로 설계한다. 조회에는 프로젝트 인증과 사건별 공유 설정을 적용한다. 응답 전체를 저장하거나 `summary.text`, `situation.people`만 사용해도 된다.

사용자가 제공한 링크온 DB 스키마를 [필드 대응 분석](../../contracts/linkone-summary-v1/linkone-db-mapping.md)에 반영했다. 링크온에는 `room.id`를 incident_id로 사용하는 안을 제안한다. 문서 속 재생성 명령을 실행하거나 DB 구조를 API 계약으로 그대로 채택하지 않았다.

## 2. 현재 코드에서 확인한 것

- [mcp_server.py](../../../prototype/mcp_server.py): `/mcp`, 프로젝트별 Bearer 인증, `submit_field_report` 1개 도구. `GET /mcp`는 조회 API가 아니며 현재 405다.
- [inbox.py](../../../prototype/inbox.py): `(project, incident_id)`와 해온 세션 연결, 중복 수신 방지, 원문·처리 이력, 인용 승인.
- [store.py](../../../prototype/store.py): `session.facts`, `session.version`, `run.final`, `run.based_on_version`, 완료·실패·이전 상황 기준 상태가 있다. 최종 보고 전용 테이블은 없다.
- [engine.py](../../../prototype/engine.py): `analysis`와 `simulation`을 구별한다. 외부 보고를 인용한 결과에는 외부 근거 참조가 붙는다.
- [server.py](../../../prototype/server.py): `/api/sessions/{sid}`는 로컬 화면용 전체 snapshot이다. 대화·첨부·모델 호출 기록이 들어 있어 그대로 외부에 제공하면 범위가 과도하다.
- 현재 수신 계약은 정확히 5개 문자열만 허용한다. [기존 전송 계약](../../implementation/17-mcp-transport.md).

이 대화의 앞선 실행 확인에서는 MCP 비활성(`mcp=false`), 기본 8862 포트 미수신, 인증 파일 존재를 확인했다. MCP·수신함 시험 16개가 통과했다. 이는 당시 실행 상태이며 새 요약 API 시험 결과가 아니다.

### 현재 데이터로 만들 수 있는 범위

현재 장부의 인원·위치와 저장된 최종 보고의 요약·판단·제안·불확실성·정보요구를 투영할 수 있다. 조회 때 LLM을 호출하지 않는다. 아직 최종 보고가 없으면 요약을 `null`로 반환한다.

장부 version은 최종 보고 생성만으로 증가하지 않는다. 반대로 장부 수정 후 기존 보고는 오래된 결과가 된다. 첨부 추가·외부 보고 수신도 반드시 장부 version을 바꾸는 것은 아니다. 따라서 version 하나로 “모든 최신 입력을 반영했다”고 표현할 수 없다.

## 3. 통신 방식 결정

검토한 방식은 일반 HTTP JSON 조회, MCP 도구 조회, 해온의 웹훅 자동 송신이다. 사용자 선택에 따라 **일반 HTTP JSON 조회를 1차 구현**한다. MCP 조회는 같은 서비스 함수를 재사용하는 후속 호환 단계다. 웹훅·송신 대기열·자동 재시도 서버는 이번 범위에 넣지 않는다.

```text
링크온 서버 ── GET 사건 요약 ──> 해온 연동 포트
            <── JSON 응답 ──── 인증 → 공유 사건 확인 → 같은 DB 시점 읽기 → 허용 필드만 구성

링크온 서버 ── MCP 현장 보고 ─> 수신함 → 담당자 인용 승인 → 기존 분석
링크온 서버 ── 다음 GET ─────> 갱신된 장부·요약·분석 상태 조회
```

기존 UI는 loopback 8860을 유지한다. 신규 조회는 기존 MCP listener(기본 8862)에 별도 경로를 추가한다. 기존 `--mcp-port`, `--mcp-host`, `--mcp-allowed-host`, `--mcp-tokens` 설정을 재사용한다. 외부 조회가 필요하면 해당 listener를 활성화해야 한다.

## 4. 제안 HTTP 계약

```http
GET /integration/v1/situation-summary?incident_id=7fa6f0ba-e99b-4e2b-8be4-36ec12d4a101
Authorization: Bearer <링크온 전용 토큰>
Accept: application/json
```

- `incident_id`: 유일한 필수 query 인자. URL 인코딩한 외부 사건 ID, 공백 제거 후 1~120자. 중복 query 인자·알 수 없는 인자는 400. `%` 인코딩 오류·비정상 UTF-8도 400.
- 사건 ID에는 한글·공백·슬래시가 있을 수 있어 경로 조각 대신 query로 전달한다. 공백 제거는 기존 사건 연결과 같은 정책을 따른다.
- 프로젝트는 인증 토큰에서 결정한다. 내부 session ID와 project query는 받지 않는다. 여러 사건은 각 ID로 따로 조회한다. 전체 사건 목록 API는 1차 범위에서 제외한다.
- 일반 REST 요청에는 JSON-RPC나 `MCP-Protocol-Version` 헤더가 필요 없다.
- Accept가 없거나 `*/*` 또는 `application/json`이면 허용한다. JSON을 명시적으로 배제하면 406 `not_acceptable`이다. GET 본문은 받지 않으며 있으면 400이다.
- 성공: HTTP 200, `Content-Type: application/json; charset=utf-8`, `Cache-Control: no-store`. JSON 본문은 아래 공통 객체 자체다.
- 본문에는 확인된 저장값만 넣는다. 숫자 미확인을 0으로 바꾸지 않고 `null`로 표현한다. 빈 목록은 `[]`다.
- GET은 장부·run·수신함·모델 호출 수를 바꾸지 않는다. 먼저 저장된 결과를 반환하고 새 분석을 시작하지 않는다.
- 오류: `{"error":{"code":"incident_not_available","message":"조회 가능한 사건이 없습니다.","retryable":false}}` 형태.
- 400 `invalid_request`, 401 `unauthorized`, 403 `host_or_origin_not_allowed`, 404 `incident_not_available` 또는 `route_not_found`, 405 `method_not_allowed`, 500 `internal_error`(retryable=true), 500 `export_too_large`(retryable=false).
- 이 REST 경로의 POST/DELETE/PUT/PATCH/HEAD/OPTIONS는 405와 `Allow: GET`이다. HEAD에는 본문을 보내지 않는다. 기존 `/mcp` 메서드 계약은 그대로 유지한다.
- 미연결·다른 프로젝트 소속·공유 꺼짐·삭제된 사건은 모두 같은 404를 사용한다. 인증 실패는 어떤 데이터도 반환하지 않는다. 내부 예외·보고 본문·토큰은 오류/로그에 노출하지 않는다.
- 응답 UTF-8 최대 262,144바이트. 초과하면 본문을 몰래 자르지 않고 `export_too_large`로 거절한다.
- 1차는 항상 JSON 200/오류를 반환한다. ETag·304·페이지네이션·부분 필드 query는 구현하지 않는다.

## 5. 응답 인자와 의미

모든 아래 고정 키를 v1 응답에 포함한다. `extensions` 내부와 미래에 추가되는 선택 키를 제외하면 새 필드를 임의로 만들어 보내지 않는다. 전체 예제는 [current.json](../../contracts/linkone-summary-v1/current.json)에 있다.

### 공통 정보

- `schema_version`: 문자열 `"1.0"`. 경로의 `/v1`은 주 버전이다.
- `source`: 문자열 `"haeon"`.
- `incident_id`: 요청한 링크온 사건 ID의 정규화값.
- `incident_title`: 해온 세션의 현재 title. 링크온 제목과 다를 수 있다.
- `mode`: `demo|live`. 자료의 실행 방식을 유지한다.
- 이 mode는 AI 실행 방식이다. 링크온 room.mode의 REAL/DRILL과 변환하지 않는다. 링크온은 자신의 실상황/훈련 구분을 별도로 표시한다.
- `state_version`: 현재 해온 장부의 0 이상 정수 version.
- `revision`: `sha256:` + 소문자 64자리 해시. 응답 내용의 동일성 판단용이며 크기 비교·시간순 정렬에 쓰지 않는다.
- `served_at`: 응답 구성 시각. 모든 외부 시각은 UTC ISO 문자열, 예: `2026-09-28T06:31:00Z`. 현장 관측 시각으로 취급하지 않는다.

### `situation`: 현재 저장 장부

- `basis`: 고정 `recorded_state`. 사용자 보고·정정으로 저장된 상태이며 독립 현장 검증을 뜻하지 않는다.
- `people.total`, `people.rescued`, `people.remaining`: 0 이상 정수 또는 `null`. 현재 facts 값을 그대로 사용하며 API에서 새 인원을 추론하지 않는다.
- `location.description`: 문자열 또는 `null`, facts.location에서 가져온다.
- `location.lat`, `location.lon`: 숫자 또는 `null`, 단위는 십진 도. 각각 위도 -90~90, 경도 -180~180이다.

명부·환자 이름·첨부·facts.notes·장부 전체·기상 원문은 1차 허용 목록에 넣지 않는다. 다만 승인해 공유하는 요약 문장 자체에 인명 등이 포함될 수 있으므로 이 API를 익명화 기능으로 설명하지 않는다.

### `summary`: 저장된 AI 보고

- `status`: `current|stale|unavailable`.
- `freshness_basis`: 고정 `ledger_version`. `current`는 보고 기준 버전과 현재 장부 버전이 같다는 뜻이다. 미처리 신고·새 첨부까지 모두 분석했다는 뜻은 아니다.
- `text`: 최종 보고의 summary 문자열. 보고가 없으면 `null`.
- `generated_at`: 선택한 run.ended_at을 UTC 문자열로 변환. 보고가 없으면 `null`.
- `based_on_version`: 선택한 run.based_on_version 정수. 보고가 없으면 `null`.
- `report_id`: 선택한 run.id를 불투명한 보고 참조로 제공. 보고가 없으면 `null`. 이 ID로 내부 실행 조회 권한이 생기지 않는다.
- `findings`: final.findings 문자열 배열.
- `recommendation`: final.recommendation 문자열 또는 `null`. 실제 조치 실행 상태가 아닌 분석 제안이다.
- `uncertainties`: final.uncertainties 문자열 배열. 불확실성을 그대로 전달한다.
- `information_requests`: `{question, reason, priority}` 배열. priority는 기존 문자열을 유지하고 없으면 `medium`. 별도 새 우선순위 추론은 하지 않는다.
- `contains_external_claims`: 선택한 run의 external_report_id 또는 final.external_report_ids가 있으면 true. 인용 검토를 사실 확정으로 바꾸지 않는다.

보고가 없으면 status=unavailable, text/generated_at/based_on_version/report_id/recommendation=null, 배열=[], contains_external_claims=false다. 접수 중이어도 HTTP 200으로 이 상태를 반환한다. 과거 보고가 있으면 그대로 반환하되 status=stale로 구분한다.

### `processing`: 별도 처리 상태

- `latest_analysis_status`: 최신 접수 analysis run의 `queued|running|completed|stale|failed|interrupted`, 없으면 `not_requested`. 기준 버전이 달라진 completed는 stale로 계산한다. 실패 상세·prompt는 내보내지 않는다.
- `pending_analysis_count`: 해당 사건에서 queued/running인 analysis 개수. simulation은 제외한다.
- `partner_pending_report_count`: 인증된 프로젝트가 이 사건에 보낸 pending/deferred 수신 보고 수. 다른 프로젝트의 보고 수는 포함하지 않는다. 외부 보고의 처리 완료나 전체 최신 입력 반영을 이 숫자로 판단하지 않는다.

`summary.status=current`이면서 `latest_analysis_status=running|failed`일 수 있다. 예전 성공 보고가 같은 장부 기준이고 새 분석은 처리 중이거나 실패한 경우다. 두 상태를 하나로 합치지 않는다.

### `extensions`: 선택 데이터의 확장 공간

v1.0은 항상 `{}`를 반환한다. 추후 합의한 이름 공간(예: `weather`, `rescue_progress`) 아래 객체를 추가할 수 있다. 기존 DB 전체나 외부 입력 객체를 그대로 복사하는 통로로 쓰지 않는다. 각 확장 항목의 출처·단위·관측 시각·확실성·허용 필드를 정한 뒤 제공한다.

## 6. 보고 선택·동시성·변경 판정

1. 하나의 명시적 SQLite 읽기 트랜잭션에서 프로젝트/사건 매핑, 공유 설정, session, 해당 session의 runs, 해당 프로젝트의 미처리 보고 수를 읽는다. 권한 확인과 데이터 읽기를 서로 다른 시점으로 나누지 않는다.
2. 후보는 `kind=analysis`, final이 있고 저장 status가 completed 또는 stale인 run이다. final의 필수 타입·기준 버전·ended_at 유효성도 확인한다. failed/interrupted와 simulation은 제외한다.
3. 후보 중 `(created_at, id)`가 가장 큰 run을 선택한다. 같은 사건의 실행은 FIFO이므로 최근 접수한 성공 분석을 제공한다. 최신 실패가 있으면 직전 성공 보고는 유지하고 processing에 실패를 표시한다.
4. 선택 보고가 없으면 unavailable, based_on_version == session.version이면 current, 다르면 stale다. 장부는 언제나 현재 값이며 stale 요약의 숫자와 다를 수 있다.
5. `revision`은 완성된 외부 JSON에서 `served_at`·`revision`을 제외한 객체를 `json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)`로 직렬화한 UTF-8 바이트의 SHA-256이다. 매핑된 incident_id, mode, 처리 상태도 해시에 포함된다.
6. 같은 장부 버전에서 새 보고가 완성되거나 processing 값이 바뀌어도 revision이 바뀐다. 조회 시각만 바뀌면 revision은 유지된다. 읽기 중 변경은 이전 또는 이후의 일관된 상태 한 개로 반환한다.

기존 `Store.snapshot()`의 모든 자료를 외부에 보내지 않는다. 외부 API 전용 읽기/투영 함수로 필요한 데이터만 선택한다. 오래된 DB 보고가 필수 타입을 만족하지 않으면 후보에서 제외하고 그 이전 유효 후보를 찾는다. 유효 후보가 없으면 unavailable이며 가짜 요약을 만들지 않는다.

## 7. 사건 공유와 인증

기존 수신용 사건 연결만으로 읽기 권한을 자동 부여하지 않는다. 연결마다 **상황 요약 공유**를 켜면 해당 프로젝트 토큰으로 조회할 수 있다. 이것은 구현 시 앱의 설정이며 이번 계획 작성의 승인 요청이 아니다.

- 새 `integration_exports` 테이블: project TEXT, incident_id TEXT, enabled INTEGER CHECK(enabled IN (0,1)), updated_at REAL. 기본키는 (project,incident_id), 두 필드는 incident_links로 복합 FK·ON DELETE CASCADE.
- 행 없음/기존 사건 마이그레이션의 기본값은 비공유다. 사건 삭제 시 공유 행도 제거된다. 서버 재시작 후 설정을 유지한다.
- 로컬 `POST /api/sessions/{sid}/integration-export`: `{project, incident_id, enabled}`. enabled는 진짜 boolean만 받는다. 기존 로컬 Host/Origin/X-Session-Token 정책을 적용한다. 매핑이 다른 세션이면 409, 연결 없음은 404.
- `ExportService.set_shared()` 결과는 `{project,incident_id,enabled,updated_at}`. 로컬 `GET /api/inbox`에 `exports` 배열을 추가해 현재 설정을 표시한다.
- 현 수신함의 연결 ID마다 공유 켜기/끄기와 조회 경로를 표시한다. 공유 켜기는 해당 사건의 현재·향후 허용 필드 자동 제공을 뜻한다. 별도 보고별 발행 절차는 1차 범위에 없다.
- 공유 해제 후 시작한 요청은 404. 이미 읽기 트랜잭션을 마친 응답이나 링크온에 저장된 복사본까지 회수하는 기능은 아니다.
- 외부 listener의 프로젝트 토큰을 재사용한다. 기존 토큰은 공유 설정이 켜진 사건에 한해 새 읽기 권한을 가진다. 토큰 파일 형식은 이번에 바꾸지 않는다.
- 최초 대상은 같은 실습망에서 서버 간 요청이다. 브라우저에 토큰을 넣거나 wildcard CORS로 공개하지 않는다. 인터넷 운영은 TLS·인증 운영 범위를 별도로 확정해야 한다.

## 8. 링크온이 받는 방법

1. 해온 담당자가 링크온 사건 ID를 연결하고 그 사건의 요약 공유를 켠다.
2. 링크온 서버가 알려진 해온 주소에 Bearer 인증 GET을 보낸다.
3. HTTP 성공 확인 → JSON 객체 파싱 → 지원하는 schema 주 버전과 incident_id 확인 → 필요한 필드 사용 순서다.
4. 요약 문장은 `summary.text`, 인원은 `situation.people`, 추가 질문은 `summary.information_requests`로 읽는다. 모르는 선택 필드는 무시한다. `null`은 미확인/미생성으로 표시한다.
5. stale이면 “이전 상황 기준”, unavailable이면 “요약 생성 전”으로 표시한다. 연결 실패 시 이전 성공 데이터는 마지막 수신 시각과 함께 보관하고 “연결 실패”를 별도로 표시한다.
6. 갱신 확인은 사용자가 새로고침하거나 링크온이 선택한 주기로 한다. 예시 자동 조회 주기는 5초이며 운영 보장값이 아니다. 직전 요청 종료 후 다음 요청을 시작해 중첩을 막는다.
7. 클라이언트 timeout 예시는 5초. 401/403/404는 자동 반복을 멈추고 인증/사건 공유 설정을 확인한다. 네트워크/500 재시도는 retryable 기준 최대 3회, 2·4·8초 지연 후 수동 재시도를 기다린다.
8. 사건 전환 뒤 늦게 도착한 이전 사건 응답은 버린다. revision은 같으면 화면 내용 교체를 생략할 수 있으나 served_at/마지막 성공 수신 표시는 갱신한다.

## 9. 반대 방향과 추후 확장

링크온 → 해온은 기존 `submit_field_report`의 report_id/incident_id/incident_title/reported_at/content를 유지한다. 수신 → pending 저장 → 담당자 인용 승인 → 분석 → 링크온 GET으로 결과 확인이다. **수신함 승인만으로 현재 장부가 바뀌지는 않는다.** 사실 반영은 기존 현재 상황 수정·명시 신고/정정을 사용한다.

추후 구조화 현장 보고가 필요하면 별도 `submit_field_report_v2`를 설계한다. 기존 5개 인자 외 임의 키를 기존 도구에 보내지 않는다. v2 후보는 schema_version, report_id, incident_id, incident_title, reported_at, content와 선택 data, corrects_report_id다. data는 허용된 위치·인원·활동 객체만 받으며 공통 검증·원문 보존·인용 승인 서비스를 재사용한다. 정확한 data 필드·단위·수량 의미는 링크온의 실제 예제를 받은 뒤 별도 계약으로 확정한다. 이번 구현 작업에는 넣지 않는다.

송신 JSON은 같은 v1 안에서 기존 필드명·자료형·의미를 유지하고 선택 키만 추가한다. 필수 키 삭제·자료형 변경·의미 변경은 `/v2`로 분리한다. 전달받은 데이터 양 증가와 더 잦은 조회는 다른 문제이므로, 대량 운영의 목록/차분/압축은 실제 필요를 확인한 뒤 설계한다.

링크온 스키마의 person_state는 구조/이송/관리/중증도/위치를 별도 축으로 갖는다. 인원 합계는 병합·미탑승·제외·삭제 처리까지 확인한 링크온 집계 결과를 받아야 한다. roster_version을 전체 사건 버전으로 쓰거나 이송을 구조 수 증가로 바꾸지 않는다. bigint 이벤트 ID는 JSON 10진 문자열로 전달하는 방향이다. 상세 대응과 아직 확인할 도메인 규칙은 위 필드 대응 분석을 따른다.

## 10. MCP 조회 호환 단계

1차 REST가 통과한 뒤 `get_situation_summary` 도구를 추가할 수 있다. 인자는 `{incident_id}` 하나이며 프로젝트 인증·공유 조건은 REST와 같다.

MCP `structuredContent`는 REST와 같은 JSON 객체다. 기존 수신 도구와 같은 방식으로 content의 text에도 JSON 문자열을 제공한다. `tools/list`에는 두 도구가 나타난다. 기존 `submit_field_report` 계약·응답은 유지한다. `/mcp`의 GET을 일반 JSON 조회로 바꾸지 않는다. 이 단계는 링크온의 REST 사용에 필수가 아니다.

## 11. 완료 판정과 미확정 입력

1차 완료는 격리 DB에서 사건별 조회·원문 비노출·공유 해제·같은 버전의 새 보고·stale/unavailable·동시 수정·인용 승인 후 조회가 검증되고, 링크온 개발자가 일반 HTTP 클라이언트로 JSON을 읽을 수 있는 상태다. 실제 링크온 연동 완료는 별도 팀 앱 시험 성공이 필요하다.

구현 설계를 막지 않는 현장 입력은 링크온 테스트 사건 ID, 접속 가능한 해온 IP, 시험망, 인증 파일 전달 경로다. 실제 연결 전에 채운다. 비밀값은 문서에 기입하지 않는다. 링크온의 백엔드 언어·화면 구조와 관계없이 위 계약을 사용할 수 있다.

단위·HTTP·브라우저 DEMO·팀 앱·LIVE 결과는 분리한다. 이번 작성에서는 신규 API 시험을 실행하지 않았다. 변경 범위는 문서와 가상 예제이며 기존 앱 코드·runtime·비밀은 유지한다.
