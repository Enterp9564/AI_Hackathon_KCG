# 13. 로컬 HTTP API 계약

> 현재 구현 기준: 2026-09-27. [목록](README.md) · 구현: [server.py](../../prototype/server.py)

## 1. 전송 규칙

기본 origin은 `http://127.0.0.1:8860`이다. 실제 실행 포트의 127.0.0.1 또는 localhost Host만 허용한다. Origin이 있으면 이 두 로컬 origin 중 하나여야 한다. 모든 POST는 GET config에서 받은 `X-Session-Token`이 필요하다. 서버 시작마다 새 토큰이 생성된다.

POST Content-Type은 `application/json`(charset 옵션 허용), Content-Length는 1~220,000바이트, 본문은 JSON 객체여야 한다. 필수값·업무 오류는 각 Store 함수에서 추가 검사한다. 오류 응답은 `{ "error":"사람이 읽는 안내" }`다.

응답은 UTF-8 JSON 또는 정적 파일, Cache-Control:no-store, nosniff와 CSP를 사용한다. CORS 외부 호출용 API가 아니다. 다중 사용자 계정은 없다. 프로젝트 연동은 이 로컬 API와 분리한 [MCP 수신 포트](17-mcp-transport.md)를 사용한다.

## 2. 조회 경로 (GET)

- `/api/config` → 200: `{token,live_available,profiles,capabilities}`. profiles는 역할별 name/model/effort, capabilities는 sessions/parallel/csv/lexical_search/inbox=true, vector_search/weather_scheduler=false, mcp는 listener 활성 여부. 모델 정보는 설정 데이터에 있지만 운영 UI에는 숨긴다.
- `/api/manuals` → 200: 공통 매뉴얼·카탈로그 Evidence 배열.
- `/api/sessions` → 200: Session 배열, 생성 최신순. 별도 `{items:...}` 래퍼 없음.
- `/api/sessions/{sid}` → 200: [02](02-data-contracts.md)의 Snapshot. 없는 세션은 404.
- `/api/monitor` → 200: `{"session_id":"고정 ID"}` 또는 null.
- `/`, `/monitor` → 같은 index.html. `/app.js`, `/style.css` 제공. 임의 파일 경로는 제공하지 않는다.

GET snapshot이나 화면 폴링은 모델 작업을 생성하지 않는다. 별도의 GET run·report·첨부 다운로드 경로는 없다. snapshot에서 ID로 찾는다.

## 3. 세션 생성 (POST /api/sessions)

입력 `{"title":"훈련 A","mode":"demo"}` → 201 Session.

title은 필수·최대 80자, mode=demo|live, 생략 기본 demo. live를 요청했는데 서버 키가 없으면 409. 키가 있다는 사실만으로 실제 모델 접근 성공을 보장하지 않는다.

## 4. 지시 접수 (POST /api/sessions/{sid}/message)

```json
{"prompt":"현재 상황을 정리해줘","kind":"analysis","assumptions":"","request_id":"request-example-01"}
```

202 Run을 반환한다. 최종 보고가 아니라 접수 결과다. kind 생략은 analysis. simulation은 assumptions 필수. request_id 필수. 같은 ID·내용 재전송도 202와 기존 run이다. 다른 내용 재사용 또는 대기 한도 초과는 409.

이후 snapshot의 runs에서 해당 id의 status를 확인한다. completed/stale이면 final, failed/interrupted이면 error를 확인한다. 모델 실패가 뒤늦게 발생해도 최초 HTTP 202가 500으로 바뀌지 않는다.

## 5. 사실 수정 (POST /api/sessions/{sid}/facts)

```json
{"version":0,"facts":{"total":5,"rescued":4,"remaining":1,"location":"가상 훈련 해역","lat":37.5,"lon":129.5,"notes":"사용자 확인"}}
```

200 갱신 Session. version은 현재와 정확히 같은 정수여야 한다. facts는 지원 필드만 허용하며 [04](04-incident-ledger.md)의 전체 교체 규칙을 따른다. 부분 patch로 오해해 기존 위치·메모를 누락하지 않는다. 버전 충돌 409, 타입·수량 오류 400.

## 6. 자료·기상·고정·삭제 (POST)

- `/api/sessions/{sid}/attachments`: `{"name":"명부.csv","content":"id,rescued\nP1,true\nP2,false"}` → 201 Attachment. 형식·CSV·크기 오류 400. multipart 업로드 없음.
- `/api/sessions/{sid}/weather`: `{}` → 200 Weather. 좌표 없음 400, 조회 중 버전 변경 409, 외부 실패 502. 실행은 [12](12-weather.md).
- `/api/sessions/{sid}/pin`: `{}` → 200 `{"session_id":"sid"}`. 기존 고정 값을 대체한다. 독립 unpin 경로는 없다.
- `/api/sessions/{sid}/delete`: `{}` → 200 `{"id":"sid","deleted":true}`. queued/running 있으면 409, 없는 세션 404. 브라우저 확인 후 요청한다.

삭제는 HTTP DELETE가 아니라 현재 POST 경로를 사용한다. PUT/PATCH/DELETE·모드 변경·세션 이름 변경 API는 구현하지 않았다.

## 7. 오류 분류

- 400: 본문 형식·크기·필수값·CSV·좌표·인원 오류.
- 403: Host/Origin 불허 또는 POST 토큰 불일치.
- 404: 없는 경로·세션. `/api/monitor/message`도 404.
- 409: 버전·동일 ID 다른 내용·진행 중 삭제·큐 초과·키 없는 LIVE.
- 500: 예기치 않은 조회/처리 실패. 내부 스택·키 대신 일반 안내.
- 502: 외부 기상 조회 실패. 모델 실패는 비동기 run에 기록.

표준 BaseHTTPRequestHandler가 처리하는 미지원 HTTP 메서드는 이 JSON 오류 계약 밖에 있을 수 있다. 공통 재시도 정책은 없다. 409는 최신 snapshot을 다시 읽고 사용자가 새 버전에서 재확인해야 한다.

## 8. DEMO 호출 예제

다음 코드는 별도 시험 DB로 실행한 서버에서 가상 DEMO 세션을 만들 때 쓰는 예제다. 키나 토큰을 출력하지 않는다.

```python
import json
import urllib.request
base = 'http://127.0.0.1:8860'
def get(path):
    with urllib.request.urlopen(base + path) as r:
        return json.load(r)
token = get('/api/config')['token']
def post(path, payload):
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','X-Session-Token':token})
    with urllib.request.urlopen(req) as r:
        return json.load(r)
session = post('/api/sessions', {'title':'API 가상 훈련','mode':'demo'})
sid = session['id']
post('/api/sessions/' + sid + '/facts',
     {'version':0,'facts':{'total':5,'rescued':4}})
run = post('/api/sessions/' + sid + '/message',
           {'prompt':'인원만 검토해줘','request_id':'demo-check-01'})
# 이후 GET snapshot의 runs에서 run['id'] 상태를 확인한다.
```

외부 프로젝트에는 로컬 세션 토큰을 공유하지 않는다. [MCP 전용 인증·사건 매핑](17-mcp-transport.md)을 사용한다.

## 추가 경로 — 2026-09-27 수신함

- `GET /api/inbox` → `{reports,links,projects}`. 전체 수신 원문·상태·처리 이력과 사건 연결을 반환한다. AI 호출 없음.
- `POST /api/sessions/:sid/inbox-link` → body `{project,incident_id}`. 현재 사건에 외부 ID 연결. 다른 사건에 이미 연결됐으면 409.
- `POST /api/sessions/:sid/inbox-action` → `{report_id,action}`. report_id는 서버 receipt ID, action은 seen/later/reject. 다른 사건이면 409. 해당 보고 반환.
- `POST /api/sessions/:sid/message` → `{inbox_report_id,kind:"analysis"}` 지원. 서버가 원문으로 인용문을 생성하고 기존 실행 큐에 등록, 202 Run 반환. 클라이언트 prompt/assumptions/request_id는 이 경로에서 사용하지 않는다. 같은 보고면 같은 Run. 다른 사건·rejected·대기열 초과는 409.
- 위 POST는 기존 Host/Origin/X-Session-Token 검사를 그대로 사용한다. `/inbox.js`가 정적 파일 허용 목록에 추가됐다.

전체 데이터와 전이 규칙은 [16](16-external-inbox.md)에 정의한다.
