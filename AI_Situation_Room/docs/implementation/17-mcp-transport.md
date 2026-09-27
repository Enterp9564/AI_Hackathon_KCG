# 17. MCP 수신 서버와 팀 프로젝트 계약

> 2026-09-27 구현. 대상: Link-One / RESAID AI 개발자. 승인 흐름은 [16](16-external-inbox.md).

## 호환 범위

`prototype/mcp_server.py`는 Python 표준 라이브러리 HTTP 서버에서 **MCP 2025-11-25 Streamable HTTP의 JSON 응답 방식**을 구현한다. 단일 `/mcp` 엔드포인트에 JSON-RPC 2.0 요청을 POST한다. 버전을 명시적으로 고정한 구현이며 최신 버전 전체 지원이나 공식 인증 통과를 의미하지 않는다.

지원: `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`.
도구: `submit_field_report` 하나. SSE, resource/prompt, sampling, 서버발 요청, task, 배치 JSON-RPC, 이전 HTTP+SSE 전송, OAuth 검색·동적 등록은 제공하지 않는다. `GET /mcp`, `DELETE /mcp`는 인증 확인 후 405. HTTP 세션 ID는 발급하지 않는 stateless 방식이다.

공식 기준: [2025-11-25 전송 명세](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [수명주기](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle), [도구](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

## 주소와 요청 헤더

기본 UI는 `http://127.0.0.1:8860`. 외부 팀원이 사용하는 주소는 별도 `http://상황실_PC_IP:8862/mcp`. 포트는 시작 옵션으로 바꿀 수 있다. MCP는 옵션을 줄 때만 활성화한다.

```http
POST /mcp
Content-Type: application/json
Accept: application/json, text/event-stream
Authorization: Bearer <해당 프로젝트의 사전 공유 토큰>
MCP-Protocol-Version: 2025-11-25
```

인증은 테스트용 프로젝트별 사전 공유 Bearer 토큰이다. 서버는 토큰에서 project를 결정한다. payload의 프로젝트명이나 내부 세션 ID는 받지 않는다. 두 프로젝트 토큰은 달라야 하며 최소 32자의 ASCII 문자열이다. 실제 값은 문서·커밋·로그에 포함하지 않는다.

Host는 loopback 또는 명시한 허용 IP/호스트와 포트가 일치해야 한다. Origin이 있으면 같은 허용 HTTP origin이어야 한다. 브라우저 직접 cross-origin 호출은 지원하지 않는다. 팀 프로젝트의 서버나 테스트 CLI에서 호출한다. 토큰 파일을 변경하면 서버를 재시작한다. 일반 UI의 X-Session-Token은 외부에 공유하지 않는다.

## 초기화 예시

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"Link-One","version":"0.1"}}}
```

응답 result는 protocolVersion, `capabilities.tools.listChanged=false`, `serverInfo.name=ai-situation-room-intake`, version 및 승인 안내를 포함한다. 다른 버전을 제안해도 지원 버전 2025-11-25를 반환하므로 클라이언트가 지원 여부를 판단한다. 이후 요청에는 협상한 버전 헤더가 필수다.

```json
{"jsonrpc":"2.0","method":"notifications/initialized"}
```

알림은 202와 빈 본문을 반환한다. 도구 실행은 반드시 request id가 있어야 한다. 알림 형태로 tools/call을 보내면 400이며 저장하지 않는다.

`tools/list`는 도구 설명과 inputSchema를 반환한다. `ping`의 result는 `{}`다. 한 요청에는 한 JSON-RPC 객체만 허용한다.

## submit_field_report 입력

다섯 필드 모두 필수 문자열이며 추가 필드는 거절한다.

- `report_id`: 1~120자. 송신자가 정한 보고 고유 ID. 프로젝트 내에서 영구적으로 재사용하지 않는다.
- `incident_id`: 1~120자. 상황실 담당자가 미리 연결한 외부 사건 ID.
- `incident_title`: 1~200자. 외부 보고의 표시용 사건명. 라우팅 기준은 연결된 incident_id다.
- `reported_at`: 1~64자. Python `datetime.fromisoformat`이 수용하는 시간대 포함 시각. 권장 `2026-09-27T14:32:00+09:00`, UTC `Z` 가능. 시각만 보내는 `14:32`는 거절.
- `content`: 1~6,000자. 미확인 정보의 원문. 파일·이미지 첨부나 구조화 환자 정보 스키마는 아직 없음.

```json
{
  "jsonrpc":"2.0","id":3,"method":"tools/call",
  "params":{
    "name":"submit_field_report",
    "arguments":{
      "report_id":"link-test-001",
      "incident_id":"training-incident-a",
      "incident_title":"A호 사고",
      "reported_at":"2026-09-27T14:32:00+09:00",
      "content":"구조 대상자 1명의 상태 변화가 보고되었습니다."
    }
  }
}
```

MCP 본문 제한은 UTF-8 **40,000바이트**. HTTP Content-Length 필수, chunked 입력은 거절한다. 연결 읽기 제한은 10초. 지나치게 미래거나 과거인 보고 시각을 자동 교정하지 않으며 패널에서 원래 보고 시각과 서버 수신 시각을 구분한다.

## 성공과 실패

성공 result는 `isError=false`, `structuredContent`와 동일 내용을 JSON 문자열로 담은 `content:[{type:"text",text:...}]`를 반환한다. structuredContent:

```json
{"receipt_id":"서버가생성한ID","report_id":"link-test-001","status":"pending","received_at":1790500000.0,"requires_human_approval":true}
```

반환 상태는 pending/deferred/sent/rejected 중 현재 저장 상태다. 재수신은 기존 접수를 반환하며 received_at도 유지한다. sent는 담당자의 지시 접수이고 모델 완료나 현장 조치 완료가 아니다. requires_human_approval은 아직 pending/deferred일 때 true다.

- 인증 누락/오류: HTTP 401, Bearer challenge.
- 허용하지 않은 Host/Origin: 403. 경로 오류: 404. 메서드 GET/DELETE: 405.
- 버전/프로토콜 형식 오류: 400. Accept 부적합: 406. 크기 초과: 413. Content-Type 오류: 415.
- 잘못된 JSON: JSON-RPC -32700. 잘못된 요청: -32600. 알 수 없는 메서드: -32601. 알 수 없는 도구: -32602.
- 필드 오류·사건 미등록·같은 보고 ID의 다른 원문: HTTP 200, **도구 result.isError=true**, 설명은 content의 text. HTTP 200만으로 접수 성공을 판정하지 않는다.
- 내부 저장 실패: HTTP 500, -32603. 비밀/traceback/보고 본문은 access log에 남기지 않는다.

재시도는 **같은 report_id + 동일 원문**으로 한다. 응답 유실 시 새 ID로 재시도하면 다른 보고로 접수된다. 정정은 새 ID와 정정 내용을 보내며 자동으로 과거 보고를 덮어쓰지 않는다.

## 공개하지 않는 기능

MCP에는 세션 열람·삭제, 사실 수정, 보고 승인, AI 실행, 채팅 조회, 모델 키 조회 도구가 없다. 승인은 loopback UI API가 담당한다. 서버 시작 정보는 주소와 활성 상태만 출력하며 토큰을 출력하지 않는다.

현재 HTTP는 암호화되지 않은 실습망용이다. 인터넷 공개나 실제 민감자료 운영에는 TLS, 조직 인증·권한, 요청률 제한, 보존 정책, 모니터링을 먼저 추가한다. 이 구현을 OAuth를 요구하는 모든 MCP 호스트에 바로 연결할 수 있다고 가정하지 않는다.
