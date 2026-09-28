# 14. 실행·보안·백업·복구

> 임시 프로젝트명: **HAEON(해온)** · 해양경찰 멀티에이전트 의사결정 지원 시스템. [명칭·소개 기준](../PROJECT_NAMING.md) (2026-09-27). ‘AI 오케스트라’는 협업 방식의 설명이며 이름에 포함하지 않는다.

> 현재 구현 기준: 2026-09-27. [목록](README.md) · 실행 명령의 기준은 [prototype/README](../../prototype/README.md)

## 1. 최소 실행 환경

Python 3.11+, 쓰기 가능한 DB 디렉터리, 현대 브라우저가 필요하다. 서버·저장·모델 전송은 Python 표준 라이브러리를 사용한다. macOS 더블클릭 실행 파일은 TLS 인증서 경로를 위해 certifi가 필요하다. Node는 JS 문법 검사 때 쓰며 앱 운영 서버 의존성은 아니다.

프로젝트 루트에서:

```sh
python3 -m prototype.server --port 8860
```

기본 DB는 prototype/runtime/room.sqlite다. 시험에는 사용자 DB 대신 별도 경로를 지정한다.

```sh
python3 -m prototype.server --port 8861 --db /tmp/situation-room-doc-test.sqlite
```

UI 서버는 루프백 전용이며 UI의 외부 호스트 바인딩 옵션은 없다. 선택적 MCP listener에만 --mcp-host/--mcp-allowed-host를 적용한다. 키 없는 직접 실행은 DEMO에 사용할 수 있다. 직접 실행한 서버는 키 파일이나 .env를 자동 읽지 않는다.

## 2. macOS 더블클릭 경로

`상황실 실행.command`의 동작:

1. 실행 파일이 있는 프로젝트 루트로 이동하고 Python 탐색 PATH를 설정한다.
2. 8860의 앱 페이지가 이미 열리면 브라우저만 열고 종료한다.
3. 신규 서버라면 certifi 설치 여부를 확인한다.
4. prototype/.secrets/openai_api_key.txt를 읽는다. 없거나 비어 있으면 안내하고 중단한다.
5. SSL_CERT_FILE과 OPENAI_API_KEY를 프로세스 환경에 설정한다. 값을 출력하지 않는다.
6. 별도 대기 스레드가 최대 약 10초 준비를 기다렸다가 브라우저를 열고, 메인에서 prototype.server를 실행한다.

키 없는 더블클릭은 현재 지원하지 않는다. certifi가 없으면 README 안내대로 `python3 -m pip install certifi`를 실행한다. Finder의 숨김 폴더 표시는 Command+Shift+.이다.

## 3. 종료·변경 적용

터미널을 열어둔 채 사용하고 Control+C로 종료한다. finally에서 HTTP 서버를 닫고 Engine의 스레드 풀 종료를 기다린다. 진행 중 외부 호출 때문에 종료가 즉시 끝나지 않을 수 있다.

코드·모델·키 변경은 서버 종료 → 재실행 → 브라우저 새로고침으로 적용한다. 실행 파일 재클릭만으로 기존 서버가 업데이트되지 않는다. 서버 재시작 시 세션 토큰도 바뀌므로 기존 탭은 새로고침한다.

## 4. 보안 경계

- API 키는 서버 메모리와 로컬 비밀 파일에 둔다. git·문서·UI·로그·발표·시험 산출물에 값을 넣지 않는다.
- 모든 요청의 Host, 존재하는 Origin을 검사하고 POST에 세션 토큰을 검사한다.
- CSP: default/script/connect self, style self+unsafe-inline, img self+data, frame-ancestors none, base-uri none.
- 응답 캐시 금지·MIME sniff 방지. 정적 제공 파일은 허용 목록만 사용한다.
- UI 문자열 escape와 서버 모델 출력 검사·근거 ID 제한을 유지한다.
- 세션 격리는 로컬 제품 데이터 경계다. 인증·사용자별 권한·암호화 저장·외부 공개 운영 보장은 없다.
- config.live_available은 키 존재 여부만 알려준다. 계정·한도·모델 접근은 실제 호출 결과로 확인한다.

외부 연동을 위해 현재 Host 검사를 끄거나 `0.0.0.0`으로 바인딩하는 것만으로 배포를 완료하지 않는다. 승인형 수신은 별도 MCP 포트로 제공한다. 명령과 비밀 파일은 [핫스팟 테스트](18-hotspot-testing.md)를 따른다. UI의 loopback 경계는 유지한다.

## 5. 백업과 복구

서버를 종료한 후 runtime 폴더를 복사한다. SQLite WAL 사용 중에는 DB 파일만 무작정 복사해 일관된 백업이라고 가정하지 않는다. 운영 중 백업은 별도 SQLite 백업 절차를 구현·검증해야 한다.

복원 시 서버를 중지하고 보관한 DB 세트를 별도 경로에서 먼저 확인한다. 기존 사용자 자료를 임의로 지우지 않는다. 다시 실행하면 Store.recover가 미완료 실행·임무를 interrupted로 표시하며 자동 재호출하지 않는다.

DB의 세션 삭제는 외부 백업·내보낸 JSON을 지우지 않는다. 보존된 시험 산출물과 사용자 데이터는 함부로 정리하지 않는다.

## 6. 배포 문서 묶음

문서·소스·기본 매뉴얼·가상 시나리오는 함께 전달할 수 있다. 비밀 파일, runtime, 원본 환경설정, 실제 사건 개인정보는 제외한다. 과거 ZIP이 새 문서를 자동 포함하지 않으므로 새 묶음은 명시적으로 만들어야 한다.

문서만 전달할 때는 상세 구현 폴더 전체, 개선사항, 루트 현재 상태·제품 요구, 실행 README, 가상 시나리오 원문을 함께 포함한다. 런타임 시험 결과 파일이 없을 수 있음을 검증 문서에 표시한다.
