# HAEON(해온) 문서 기반 재구현 실행 계획

> **For agentic workers:** 사용 가능한 환경에서는 superpowers:executing-plans로 작업별 구현·검증을 진행한다. 이 스킬이 없는 AI 플랫폼도 아래 인터페이스·판정 기준으로 진행할 수 있다. 개발 보조 에이전트 생성은 요구하지 않는다.

**Goal:** Python HTTP·SQLite·HTML/CSS/JavaScript로 현재 해온의 세션·장부·역할별 병렬 검토·화면·승인형 MCP 수신 기능을 재구현한다.

**Architecture:** 로컬 HTTP 서버와 세션별 작업 큐, 공용 SQLite, 서버측 모델 provider, 약 1초 조회형 UI를 사용한다. 독립 요원은 병렬, 같은 세션 요청은 순차다. MCP는 별도 선택적 listener로 미확인 보고를 받고 담당자의 인용 승인 후 기존 지시 큐에 넣는다.

**Tech Stack:** Python 3.11+ 표준 라이브러리, SQLite WAL, HTML/CSS/JavaScript. Node는 개발 검사 도구, certifi는 macOS 실행 편의 의존성이다.

**Spec:** [기능별 구현 명세](../implementation/README.md). 코드 없는 전달에서는 [통합 명세](HAEON_REBUILD_SPEC.md)의 동일 절을 읽는다.

## 공통 제약

- 이름 HAEON(해온), AI 오케스트라는 역할 조율 방식의 설명. 모든 역할 gpt-6-luna/medium은 현재 설정이며 제공자 사용 가능 여부는 실행 시 확인한다.
- UI에서 모델/추론 수준을 숨기고 LIVE/DEMO를 구별한다. LIVE 실패의 DEMO 대체는 금지한다.
- 세션 원문·명부 정정 이력·출처를 보존한다. 모르는 인원은 0으로 만들지 않는다.
- 사용자 소유 runtime/비밀 파일을 복사·삭제·출력하지 않는다. 새 임시 DB·가상 자료로 시험한다.
- 현장 출동 명령·물리 예측·실측·벡터 RAG·왕복 MCP 연동은 현재 구현으로 주장하지 않는다.
- 현재 복원과 22의 개선은 분리한다. UI 애니메이션으로 미완료 서버 단계를 감추지 않는다.
- 단위/HTTP/브라우저/LIVE/실제 팀 앱을 따로 기록한다. 체크박스는 앞으로 수행할 작업이며 완료 기록이 아니다.

## 먼저 확인할 실패 조건

1. 응답 유실 후 같은 ID 재전송 → run/원문 1개. 작업 1·3·6에서 확인.
2. 세션 전환 중 늦은 보고·snapshot → 원래 세션에만 저장/표시. 작업 3·6에서 확인.
3. 장부 저장 후 요원 실패 → 저장된 사실과 성공 보고 보존, run은 failed. 작업 2·3에서 확인.
4. 외부 인용·가정·후속 요약 → 사실로 자동 승격되지 않음. 작업 3·7에서 확인.
5. 같은 외부 보고 승인/거절 경합·삭제 사건 재전송 → 한 종결 상태, 다른 사건 유입 없음. 작업 7·8에서 확인.

## 작업 1. 영속 저장과 세션

**파일:** prototype/__init__.py, store.py; tests/test_store.py.
**입력:** title/mode 및 session ID. **출력:** Session·Snapshot, Store 메서드(20), 3개 테이블(02).

- [ ] 세션 A/B 생성·재열기·격리, version 충돌, 동일 request_id/다른 내용 충돌을 검사하는 테스트를 작성한다. A.total=8/B.total=2가 각각 유지되어야 한다.
- [ ] Store 없이 테스트가 실패하는지 확인한 뒤 uid/text/encode/db와 session/object/settings 저장을 구현한다.
- [ ] enqueue의 run/message/received event를 원자 저장한다. 같은 ID+내용은 같은 run, 9번째 미완료 요청은 거절한다.
- [ ] pending 삭제 거절, 유휴 삭제 후 객체·고정 제거, recover의 interrupted 전환을 구현한다.
- [ ] `python3 -m unittest prototype.tests.test_store -v`로 해당 테스트 모두 통과를 확인한다. 시험 DB 경로와 결과를 남긴다.

## 작업 2. 사실 장부·정정·버전

**파일:** incident.py, store.py; tests/test_incident.py.
**입력:** Session+patch+expected_version. **출력:** 새 Session, audit event, run.update_applied.

- [ ] 21 사례 B의 이름 정정에서 같은 ID·나머지 속성 보존, distribution 전체 교체, 9명 합계 거절을 먼저 검사한다.
- [ ] merge_update/receipt와 apply_update를 구현한다. facts/conditions는 부분 병합, roster/patients/assets는 ID별 병합, distribution은 전체 교체다.
- [ ] simulation·외부 인용·stale patch 차단, patch 반복 무변경, 다른 patch 재사용 충돌을 검사한다.
- [ ] set_facts의 전체 교체와 remaining 예외, 좌표 변경 기상 해제, 명시 HH:MM 반영을 구현한다.
- [ ] `python3 -m unittest prototype.tests.test_store prototype.tests.test_incident -v`를 통과시키고 원문 보존을 확인한다.

## 작업 3. Provider 계약과 실행 큐

**파일:** models.py의 DemoModel/ModelError, engine.py; tests/test_engine.py.
**입력:** 06의 respond(role,stage,context). **출력:** Tasks/Calls/Report·Run 종료 상태.

- [ ] fake provider로 두 독립 요원 실행 구간 중첩, 같은 세션 FIFO, 다른 세션 진행, 미래 큐 원문 제외 테스트를 먼저 작성한다.
- [ ] 4 session workers/6 agent workers/6 call slots, run 중복 예약 방지와 drain을 구현한다.
- [ ] plan 검증→현재 patch→선택 요원 동시 제출→critic→final 순서, 무임무 receipt 경로를 구현한다.
- [ ] 보고 근거 ID 검증, 질문·출동안 정규화, timeline/report_ids/basis_version/assumptions를 결합한다.
- [ ] 한 요원 실패에 나머지를 기다린 뒤 run.failed, 중간 장부/성공 보고 보존, stale 표시를 검사한다.
- [ ] `python3 -m unittest prototype.tests.test_engine -v`가 통과하고 조회만으로 calls가 늘지 않는지 확인한다. 목표 개선 경로 22는 이 단계에 몰래 섞지 않는다.

## 작업 4. 근거·자료·등록 세력·수동 기상

**파일:** tools.py, manuals.py, manuals/basic-response-manual.md, manuals/donghae_assets.json, Store.add_attachment/set_weather.
**입력:** 가상 첨부·query·현재 Session·기상 mock. **출력:** Evidence[], 후보 출동안, Weather.

- [ ] 07의 CSV ID/집계 오류, BOM, 관련/무관 TXT, 최대 5개/16,000자 선택을 검사한다.
- [ ] 통합 명세 부록의 기본 매뉴얼과 18개 자산 카탈로그를 파일로 복원한다. 원본 근거·보조 초안 표시를 유지한다.
- [ ] 08의 키워드 후보·ID 정규화를 구현한다. 카탈로그를 실시간 위치나 실제 출동으로 표현하지 않는다.
- [ ] 기상 mock 성공/실패/조회 중 version 변경과 좌표 변경을 검사한다. timeout=15, 요청·반환 좌표/시각/단위 보존.
- [ ] 해당 단위 테스트를 통과시킨다. 실제 기상 호출은 별도 환경 확인 후 판정하고 mock 통과를 실제 응답 성공으로 쓰지 않는다.

## 작업 5. 로컬 HTTP

**파일:** server.py; tests/test_http.py.
**입력:** 13의 모든 GET/POST. **출력:** 정확한 상태코드·JSON·정적 페이지.

- [ ] 127.0.0.1 임시 포트로 config→세션→facts→message→snapshot 왕복을 검사한다.
- [ ] Host/Origin/쓰기 token, JSON 객체·220,000바이트 제한, 정적 allowlist/CSP를 구현한다.
- [ ] 202는 접수임을 유지하고 중복·충돌·400/403/404/409/502 경계를 검사한다.
- [ ] `python3 -m unittest prototype.tests.test_http -v`를 실행한다. 수신함 관련 테스트는 작업 7 후 추가한다.

## 작업 6. 담당자 화면과 고정 상황판

**파일:** static/index.html, app.js, style.css. **입력:** Snapshot/Config/Manuals. **출력:** /와 /monitor.

- [ ] 10·11·19의 배치·상태·DOM 연결을 구현한다. 최초 키 없음 DEMO/키 있음 LIVE 기본을 구별한다.
- [ ] Enter/Shift+Enter/한글 조합, 즉시 피드백, disabled 중복 클릭, 초안/재시도 ID 보존을 구현한다.
- [ ] generation/target 검사를 넣고 A 실행 중 B 전환·늦은 응답 무시·스크롤 보존을 확인한다.
- [ ] 현재 장부/요원/보고 상세, 근거/원문/정정 이력, 전송 실패/stale/interrupted를 확인한다.
- [ ] A 고정/B 선택, 고정 삭제 빈 화면, 복귀/전체화면을 확인한다.
- [ ] `node --check prototype/static/app.js`와 실제 브라우저 1920×1080/1280×720/390×844 검사를 별도 기록한다. 긴 보고·모션 감소·모델명 비노출을 확인한다.

## 작업 7. 외부 수신함과 인용 승인

**파일:** inbox.py, store.py, engine.py, static/inbox.js/app.js/index.html; tests/test_inbox.py, test_send.cjs.
**입력:** project+외부 5필드, 사건 매핑, receipt ID. **출력:** 원문 수신/승인 Run/이력.

- [ ] receive가 facts/version/messages/runs/calls를 바꾸지 않는 테스트를 작성한다.
- [ ] 16의 테이블·UNIQUE·BEGIN IMMEDIATE·원문 보존·중복/충돌·seen/later/reject/sent를 구현한다.
- [ ] 승인과 _enqueue를 같은 트랜잭션으로 묶고 큐 초과 시 승인도 롤백한다.
- [ ] 인용 update 차단·최소 intel·외부 출처의 후속 요약 전파/일반 사실 추출 제외를 구현한다.
- [ ] 승인/거절 경합, 다른 사건 승인, 삭제 사건 재수신, 초안/가정/모드 보존을 확인한다.
- [ ] `python3 -m unittest prototype.tests.test_inbox -v`, `node prototype/tests/test_send.cjs`, `node --check prototype/static/inbox.js`를 실행하고 브라우저 수신함을 별도 검사한다.

## 작업 8. MCP 전송과 송신 도구

**파일:** mcp_server.py, prepare_mcp.py, send_field_report.py, server.py; tests/test_mcp.py.
**입력:** 프로젝트 토큰·MCP JSON-RPC. **출력:** submit_field_report 결과.

- [ ] 17의 초기화/알림/도구 목록/호출·MCP 버전·Host/Origin/토큰/Accept/크기 검사를 작성한다.
- [ ] 별도 listener, 요청 ID 없는 tools/call 거절, 프로젝트 식별은 토큰으로만 결정하도록 구현한다.
- [ ] HTTP 200 + isError=true 실패를 검사하고 report_id+동일 원문 재시도를 보존한다.
- [ ] 토큰 생성 파일 권한·덮어쓰기 방지·CLI redirect 거부를 구현한다. 키/토큰 값 출력 금지.
- [ ] `python3 -m unittest prototype.tests.test_mcp prototype.tests.test_http -v`로 loopback 검증한다. 실제 핫스팟/상대 앱 검증은 18의 합동 절차로 따로 수행한다.

## 작업 9. LIVE와 전체 인수

**파일:** models.py ResponsesModel, 실행 파일, README/PROGRESS, tests/test_models.py.
**입력:** 서버 환경의 사용자 키·가상 청해호 15건. **출력:** 실제 호출 metadata와 판정 기록.

- [ ] 먼저 mock 전송으로 model/medium/store=false, 90초 timeout, JSON 파싱·incomplete/refusal·오류 비노출을 검사한다.
- [ ] API 키는 사용자가 로컬 비밀 파일/환경변수에 입력한다. 이 문서에 키를 추가하지 않는다. API 계정 접근이 안 되면 LIVE 미실시로 기록한다.
- [ ] 별도 LIVE 세션에서 15의 청해호 순서와 정답을 검증한다. 실제 호출은 비용이 발생하므로 실행 주체의 승인 범위를 따른다.
- [ ] 전체 Python discover, JS 검사, 브라우저, LIVE, 실제 상대 앱의 결과를 따로 기록한다. 이전 실패/재실행 기록을 보존한다.

## 작업 10. 최신 요구 개선과 전달

**파일:** 22에서 선택한 기능·해당 테스트·관련 명세.

- [ ] 현재 복원 인수 결과를 먼저 확정하고 P0 빠른 배정/핵심 1~2건의 새 계약을 상세 설계한다.
- [ ] 새 기능 실패 사례→최소 구현→회귀→시간/효율 실측 순으로 진행한다. 현재 요구와 코드 차이를 완료로 숨기지 않는다.
- [ ] 13/PROGRESS/상세 명세를 업데이트하고 통합 전달본을 재생성한다.
- [ ] 전달 결과에는 구현 파일·실행법·검증 결과·미완료·재현 가능한 다음 작업을 명시한다. Git commit/push는 실제 환경과 사용자 요청 범위를 따른다.

## 검토 결론

기능별 명세 01~18을 폐기하지 않고 연결에 필요한 19~22를 보완했다. 작업 1~9가 현재 앱의 주 기능 복원, 작업 10은 최신 사용자 요구와 구현 차이를 해소하는 단계다. 실제 문서 전용 재구현은 아직 실행하지 않았으므로 동일성·성능을 보장하지 않는다.
