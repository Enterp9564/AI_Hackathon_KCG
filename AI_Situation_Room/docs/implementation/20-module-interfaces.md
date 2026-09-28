# 20. 모듈 연결·설정·트랜잭션 계약

> 2026-09-28 소스에서 함수 시그니처를 대조했다. 코드 본문을 전달하지 않아도 모듈 경계를 맞추기 위한 문서다. 아래 시그니처는 현재 구현, 개선 계약은 22에서 분리한다.

## 조립 순서

1. Store(db_path)로 디렉터리·3개 기본 테이블 생성 후 recover().
2. Engine(store, demo_model, live_model) 구성. 테스트에서는 모의 provider를 주입한다.
3. make_server가 Inbox(store)를 초기화해 외부 연결/수신 테이블 추가. 매번 초기화해도 기존 자료를 지우지 않는다.
4. --mcp-port가 지정됐을 때만 프로젝트 토큰 파일을 읽고 같은 Store를 쓰는 Inbox로 별도 MCP listener 구성.
5. MCP serve_forever는 daemon thread, UI server는 main에서 실행. 종료 시 두 서버를 닫고 Engine.close()로 작업자 종료를 기다린다.

UI 기본 127.0.0.1:8860. MCP 포트는 기본 활성값이 없고 8862를 실습 예시로 쓴다. DB 기본 prototype/runtime/room.sqlite. CLI의 --db/--port/--mcp-port/--mcp-host/--mcp-allowed-host(반복 가능)/--mcp-tokens를 유지한다. MCP만 명시적 LAN 노출을 허용한다.

## 반환값·부작용

- Store.create_session/set_facts/apply_update → Session. list_sessions → Session[]. snapshot → Snapshot.
- Store.enqueue/_enqueue/get_run/update_run/finish_run → Run. enqueue는 실행하지 않고 저장만 한다.
- add_task/update_task → Task, add_attachment → Attachment, event/record_call → 생성된 객체.
- delete_session → {id,deleted:true}. pin/set_weather/recover/close는 호출 결과 데이터 대신 저장·정리 부작용이 중심이다. pinned → ID 또는 null.
- Engine.submit → 접수된 Run, 비동기 실행 예약. wait → 시험용 Future 대기(30초). process → run/task/call/event를 갱신한다.
- Model.respond → (JSON 결과 객체, {model,usage,response_id}). DB에 직접 쓰지 않는다.
- merge_update → 원본을 바꾸지 않는 새 Session 사본. 네트워크·DB 부작용 없음.
- receipt → Report. 정보요구/출동안을 포함하되 모델 재호출 없음.
- evidence_for → Evidence[], weather → Weather, manual_evidence → 공통 Evidence[].
- Inbox.link → 연결 객체, list → {reports,links,projects}, receive/get/act → 수신 Report, enqueue → Run, quote → 서버 생성 인용 문자열.
- make_server/make_mcp_server → 실행 전 HTTPServer 객체. port=0은 테스트용 임시 포트이며 server_port로 실제 포트 확인.

KeyError는 존재/소속 오류, Conflict(ValueError)는 버전·중복·정책 충돌, ValueError는 입력 오류, ModelError는 모델 단계 실패다. HTTP 매핑은 13·17에 따른다. 네트워크 오류 본문이나 자격증명을 사용자 오류로 그대로 복사하지 않는다.

## 트랜잭션 소유권

Store.db는 RLock, 새 SQLite connection(timeout 10), foreign_keys=ON, 성공 commit/예외 rollback/항상 close를 소유한다. 모델·외부 날씨 호출은 이 락 밖이다. JSON 객체 간 관계 검사는 서버에서 수행한다.

일반 지시 접수는 세션 확인·멱등 검사·대기 상한·run/사용자 메시지/received event를 한 트랜잭션으로 묶는다. Inbox.enqueue는 BEGIN IMMEDIATE 안에서 같은 연결의 Store._enqueue를 호출해야 한다. 별도 Store.enqueue 트랜잭션을 열어 승인 상태와 지시가 따로 저장되게 만들면 안 된다.

장부 patch는 별도 트랜잭션이다. 후속 요원 실패가 이전 장부 성공을 되돌리지는 않는다. 작업 중 사용자 수정은 버전으로 구분하며 최종 보고를 stale로 표시한다. session.version은 첨부·대화 접수·고정·수신만으로 증가하지 않는다.

## 복원에 필요한 상수

세션 작업자=4, 요원 작업자=6, 모델 semaphore=6, 세션별 queued/running 상한=8. prompt=8,000자, assumptions=3,000자, request_id=120자, title=80자. 문맥=JSON 180,000자, 모델 결과=JSON 30,000자. role 배정 최대 3개/중복 불가, 질문 결과당 최대 12개, 출동안 결과당 최대 20개. prompt 지침의 질문 최대 5와 UI 앞 2개 표시는 별도 규칙이다.

LIVE timeout 90초, max_output_tokens=6000, 전 역할 medium, model=gpt-6-luna, store=false. 이는 저장소 설정이며 현재 제공자의 가용성 검증은 아니다. 실행 환경에 접근 가능한 모델이 없으면 명시적으로 보고하고 사용자 결정 없이 다른 모델·DEMO로 대체하지 않는다.

DEMO 기본 delay=.5초에 commander×1/intel×1.4/sar×1.8/resource×1.1/critic×1을 사용한다. 병렬·진행 표시 시험용 지연이며 실모델 속도가 아니다. 기본 세 전문요원, ‘만’+명부/인원/기상은 intel, ‘만’+자원은 resource로 좁힌다. 결론 문장의 바이트 단위 동일성보다 06의 필드·분기·명시적 DEMO 표시를 재현한다.

## 현재 호출 시그니처

self는 인스턴스 참조다. 아래는 연결에 쓰이는 함수와 메서드이며 private 저장 헬퍼는 Inbox와 원자적 저장을 구현할 때 참고한다. 자동 추출한 시그니처만으로 구현을 끝내지 말고 02~18의 동작 계약을 함께 적용한다.

### prototype/store.py

```python
class Conflict
def uid()
def encode(value)
def text(value, limit=8000)
class Store
    def __init__(self, path)
    def db(self)
    def _session(self, db, sid)
    def _put_session(self, db, data)
    def _add(self, db, sid, kind, data)
    def _items(self, db, sid, kind)
    def _object(self, db, oid, sid=None, kind=None)
    def _update(self, db, oid, data)
    def create_session(self, title, mode='demo')
    def delete_session(self, sid)
    def list_sessions(self)
    def snapshot(self, sid)
    def set_facts(self, sid, facts, expected_version)
    def apply_update(self, rid, patch, expected_version)
    def enqueue(self, sid, content, kind, assumptions, request_id)
    def _enqueue(self, db, sid, content, kind, assumptions, request_id, external_report_id=None)
    def get_run(self, rid, sid=None)
    def update_run(self, rid, **fields)
    def event(self, sid, label, event_type='progress', **data)
    def add_task(self, run, role, instruction, reason)
    def update_task(self, tid, **fields)
    def record_call(self, sid, **fields)
    def finish_run(self, rid, final, status='completed', error=None)
    def add_attachment(self, sid, name, content)
    def set_weather(self, sid, expected_version, weather)
    def recover(self)
    def pin(self, sid)
    def pinned(self)
```

### prototype/incident.py

```python
def count(value)
def string(value)
def merge_update(session, patch)
def receipt(session, source_id, summary, information_requests=None, dispatch_orders=None)
```

### prototype/engine.py

```python
class Engine
    def __init__(self, store, demo_model=None, live_model=None)
    def submit(self, sid, prompt, kind, assumptions, request_id, inbox_report_id=None)
    def drain(self, sid)
    def wait(self, rid)
    def close(self)
    def call(self, run, role, stage, context, slot_held=False)
    def validate(self, result, stage, context)
    def validate_requests(requests, source)
    def information_requests(items, source)
    def validate_dispatch_orders(orders)
    def dispatch_orders(model_orders, manual_orders)
    def agent(self, run, assignment, context)
    def process(self, rid)
```

### prototype/models.py

```python
def effort(role)
class ModelError
class ResponsesModel
    def __init__(self, key=None)
    def respond(self, role, stage, context)
class DemoModel
    def __init__(self, delay=0.5)
    def respond(self, role, stage, context)
```

### prototype/tools.py

```python
def evidence_for(snapshot, query)
def weather(lat, lon)
```

### prototype/manuals.py

```python
def _read_catalog()
def asset_catalog()
def manual_evidence()
def _unit(asset_id)
def _order(asset_id, order, reason, priority='high')
def recommended_dispatch(prompt, session)
def normalize_orders(items)
```

### prototype/inbox.py

```python
class Inbox
    def __init__(self, store)
    def project(project)
    def link(self, sid, project, incident_id)
    def list(self)
    def _get(self, db, report_id)
    def get(self, report_id)
    def _save(self, db, report)
    def receive(self, project, payload)
    def act(self, sid, report_id, action)
    def quote(r)
    def enqueue(self, sid, report_id)
```

### prototype/server.py

```python
def make_server(store, engine, port=8860, mcp_enabled=False)
def main()
```

### prototype/mcp_server.py

```python
def validate_tokens(tokens)
def load_tokens(path)
def make_mcp_server(inbox, tokens, host='127.0.0.1', port=8862, allowed_hosts=())
```

## 브라우저 모듈 연결

app.js를 먼저 defer로 읽고 inbox.js를 그 뒤에 읽는다. app.js의 api(path,data), send({report=null}={}), selectSession(id), sid/config/snapshot은 같은 페이지의 실행 환경에서 수신함과 연결된다. 일반 전송과 외부 인용은 send를 공유하며 합성 키보드 이벤트로 우회하지 않는다.

브라우저 상태는 선택 sid·snapshot·runId·pinned·generation·lastSync·polling·requestKind·drafts Map·retries Map이다. 서버 사실의 원본은 SQLite이며 DOM이나 localStorage가 아니다. localStorage는 마지막 선택 ID만 보관한다. 약 1초 앱 폴링·2초 inbox 폴링·별도 시계 갱신을 두며 중복 fetch와 늦은 세션 응답을 막는다.

재구현 중 모듈을 분리하더라도 외부 계약·세션 격리·초안 보존을 유지한다. 새 프레임워크·빌드 체계를 추가하지 않는 현재 요구를 우선한다.
