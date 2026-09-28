# 18. 핫스팟 연결 준비와 합동 테스트

> 임시 프로젝트명: **HAEON(해온)** · 해양경찰 멀티에이전트 의사결정 지원 시스템. [명칭·소개 기준](../PROJECT_NAMING.md) (2026-09-27). ‘AI 오케스트라’는 협업 방식의 설명이며 이름에 포함하지 않는다.

> 다른 두 프로젝트는 아직 완성 전이다. 지금은 상황실 수신 서버·계약·테스트 송신 도구까지 준비했다. 실제 팀 앱/핫스팟 장비 연결은 별도 시험해야 한다.

## 1. 한 번만 인증 파일 생성

명령은 `prototype/`가 들어 있는 프로젝트 루트에서 실행한다. GitHub에서는 `AI_Situation_Room/`로 이동한 뒤 실행한다.

```sh
python3 -m prototype.prepare_mcp
```

생성 위치: `prototype/.secrets/mcp/`.

- `clients.json`: 상황실 서버만 보관. 두 프로젝트 토큰 포함.
- `link-one.token`: Link-One 개발자에게만 전달.
- `resaid-ai.token`: RESAID AI 개발자에게만 전달.

디렉터리는 0700, 파일은 0600으로 생성한다. 이미 하나라도 있으면 덮어쓰지 않는다. 토큰 값은 출력하지 않으며 `.secrets/`는 Git 제외다. 개인별 토큰을 팀의 안전한 수단으로 전달하고 저장소에 올리지 않는다. 교체가 필요하면 `--directory`로 별도의 비밀 디렉터리에 새 세트를 만들고 서버/클라이언트 경로를 함께 바꾼다.

## 2. 먼저 한 PC에서 확인

```sh
python3 -m prototype.server --mcp-port 8862
```

상황실 화면 `http://127.0.0.1:8860`에서 DEMO 사건을 만든다. **Link-One → 현재 사건 연결 설정**에서 `training-incident-a`를 연결한다. RESAID AI에도 같은 ID를 연결하면 양쪽이 같은 상황실 사건을 사용한다. 실제 사건은 팀이 합의한 ID를 사용한다.

다른 터미널에서:

```sh
python3 -m prototype.send_field_report \
  --url http://127.0.0.1:8862/mcp \
  --token-file prototype/.secrets/mcp/link-one.token \
  --incident-id training-incident-a \
  --incident-title 'A호 사고' \
  --report-id link-test-001 \
  --reported-at '2026-09-27T14:32:00+09:00' \
  --content '구조 대상자 1명의 상태 변화가 보고되었습니다.'
```

RESAID 시험은 토큰 파일을 `resaid-ai.token`, report-id를 `resaid-test-001`로 바꾼다. 도구는 MCP 초기화·도구 목록 확인·보고 제출을 수행하며 실제 AI를 호출하지 않는다. HTTP redirect는 인증 정보를 다른 주소로 보내지 않도록 따르지 않는다.

같은 명령을 다시 실행해 기존 receipt_id가 반환되는지 확인한다. 재시도 동안 reported-at과 본문도 동일하게 유지한다. 새로운 보고를 시험할 때만 report-id를 바꾼다.

## 3. 같은 핫스팟에서 접속

1. 상황실 PC와 팀원 PC를 같은 휴대폰 핫스팟에 연결한다.
2. 상황실 PC의 해당 Wi-Fi IPv4 주소를 네트워크 설정에서 확인한다. 주소가 바뀌면 허용 호스트와 팀원 접속 주소도 바꾼다.
3. 기존 서버를 정상 종료(Ctrl+C)하고 아래처럼 시작한다. `172.20.10.2`는 예시이며 실제 IP로 대체한다.

```sh
python3 -m prototype.server \
  --mcp-port 8862 \
  --mcp-host 0.0.0.0 \
  --mcp-allowed-host 172.20.10.2
```

4. OS 방화벽에서 필요한 경우 Python의 해당 네트워크 수신을 허용한다.
5. 팀원은 자기 프로젝트 토큰 파일을 사용하고 송신 도구의 URL을 `http://172.20.10.2:8862/mcp`로 바꾼다. 자기 PC의 `127.0.0.1`은 상황실 PC가 아니다.
6. UI는 계속 상황실 PC의 `127.0.0.1:8860`에서 담당자가 조작한다. 8860 담당자 API를 LAN에 공개하지 않는다.

핫스팟이 기기 간 통신을 차단하면 같은 SSID라도 연결되지 않는다. 이 경우 기기 격리 설정을 확인하거나 기기 간 통신을 허용하는 시험 공유기로 바꾼다. 핫스팟 공인 IP나 휴대폰 게이트웨이 IP를 상황실 주소로 쓰지 않는다. 포트 포워딩은 필요 없다.

## 4. 합동 인수 순서

- 보고 수신 → 프로젝트 버튼에 건수/은은한 강조. 이때 채팅·실행 수·현재 상황/버전이 그대로인지 확인.
- 패널에서 출처·사건·시각·원문 확인. 미확인 주장 안내 확인.
- 채팅 초안과 시뮬레이션 가정을 작성한 상태에서 인용 전송. 초안·가정·선택 모드 보존 확인.
- 출처가 있는 채팅 1개 → 상황실장 배정 → 요원 검토 → 최종 보고. 상황판 사실 값은 자동 변경되지 않아야 함.
- 동일 보고 재전송·인용 재시도 → 보고·지시가 추가로 생성되지 않아야 함.
- 나중에 → 대기 목록 유지. 반영 안 함 → 이력 남고 AI 실행 없음.
- 다른 사건 보고 → 현재 사건에서 전송 버튼 비활성. 연결 사건으로 이동 후에만 전송.
- 네트워크를 잠시 끊었다 복구한 뒤 동일 보고로 재시도. 접수 결과 확인.
- 잘못된 프로젝트 토큰·미등록 사건·같은 보고 ID의 다른 내용은 오류 확인.
- 서버 재시작 → 원문/상태/이력 유지. 중단된 AI 지시는 자동 재실행되지 않음.

실제 LIVE 검증은 별도로 수행한다. DEMO 성공을 실제 모델 검토 또는 현장 데이터 검증으로 기록하지 않는다.

## 5. 문제 확인

- Connection refused/timeout: 서버 실행·PC 주소·핫스팟 격리·방화벽·포트 확인.
- 401: 해당 프로젝트의 `.token` 파일인지, 서버의 clients.json과 짝이 맞는지 확인. 값 출력 금지.
- 403: `--mcp-allowed-host`와 접속 IP 일치 확인. 브라우저 직접 송신은 허용된 Origin 조건도 확인.
- 400: MCP 버전과 JSON 형식 확인.
- HTTP 200인데 isError=true: 사건 연결 또는 다섯 필드·보고 ID 충돌 확인.
- 화면에서 MCP 비활성: `--mcp-port` 없이 실행한 경우. 기존 프로세스를 종료하고 옵션으로 재실행.
- sent인데 완료 보고 없음: 수신함의 지시 ID와 해당 사건의 실행 이력에서 queued/running/failed/interrupted 확인.

## 6. 개발자 검증 명령

```sh
python3 -m unittest discover -s prototype/tests -q
node --check prototype/static/app.js
node --check prototype/static/inbox.js
node prototype/tests/test_send.cjs
```

Playwright와 Chromium이 설치된 개발 환경에서는 `node prototype/tests/browser_inbox.cjs`. 설치된 Chrome을 쓸 때는 `CHROME_CHANNEL=chrome`을 앞에 붙인다. 패키지가 전역/별도 경로라면 NODE_PATH를 환경에 맞게 지정한다. 브라우저 검증은 임시 DB·임시 포트·시험 토큰으로 수행하고 종료 시 서버를 닫고 시험 토큰 파일을 지운다. 기존 runtime은 사용하지 않는다.

2026-09-27 결과: Python 59개(저장/Engine/모델/장부 및 HTTP 포함) 통과, 공유 send 검증 통과, Chrome 브라우저 통과. 기본 Playwright Chromium 실행 파일이 없어 첫 실행은 실패했고 설치된 Chrome으로 재실행했다. 실제 핫스팟·타 프로젝트 앱·이번 변경의 LIVE 모델 실행은 미실시.
