# AI 상황실 프로토타입 구현 계획

> 과거 구현계획 보존본. 현재 모델·UI·개발 우선순위는 [2026-09-26 인수인계](../../../13_현재상태_요구사항_인수인계.md)를 우선한다. 이 문서의 당시 설정·체크 표시는 최신 전체 검증을 뜻하지 않는다.

> **For agentic workers:** superpowers:executing-plans로 이 작업에서 직접 구현한다.

**Goal:** 세션 기억, 상황실장 배정, 독립 요원 병렬 작업, 검증·최종 보고와 가정 기반 조언을 실제 저장·실행하는 로컬 프로토타입.
**Architecture:** Python 표준 라이브러리 HTTP 서버 + SQLite 영속 저장 + 서버 작업자. HTML/CSS/JavaScript 담당자·모니터링 화면은 읽기 스냅샷을 갱신한다. 모델 어댑터는 OpenAI Responses와 명시적인 결정론적 데모 실행을 분리한다.
**Tech Stack:** Python 3.11+, SQLite, native web UI, unittest.
**Spec:** 01, 04, 11, 12 문서.

## Global Constraints
- 실제 모델 `gpt-6-luna`, 상황실장 high·네 요원 medium. 키는 환경변수로만 읽는다.
- 모든 소유 데이터의 session_id 검사. 가정과 사실 분리. 새 세션은 빈 기억.
- 서버는 127.0.0.1 전용. 발표 HTML을 변경하지 않는다.
- 키가 없으면 데모 모드임을 지속 표시. API 실패를 데모 응답으로 대체하지 않는다.
- 첫 프로토타입: 세션/CSV/텍스트 근거/조건 비교/수동 기상 경로. Chroma 벡터 검색·MCP·자동 기상 스케줄·실제 현장 예측은 미구현으로 표시한다.

## Review Focus
- 다른 세션의 ID 참조·늦은 콜백: 원래 세션에만 저장.
- 같은 전송 재시도: 한 번만 접수·실행.
- 사실 정정 중 이전 실행 완료: 이전 버전 표시.
- 근거가 없는 시뮬레이션: 조건부 설명·판단 보류, 사실 덮어쓰기 없음.
- 서버 재시작·외부 응답 실패: 작업 중단·오류 상태와 입력 보존.

## Task 1 — 영속 저장과 세션 경계
Files: prototype/store.py, prototype/tests/test_store.py
Interface: Store.create_session(title,mode), snapshot(sid), set_facts(sid,facts,expected_version), enqueue(sid,text,kind,assumptions,request_id), add_attachment(sid,name,content).
- [x] 실제 SQLite에서 빈 세션·교차 조회·중복 전송·버전 충돌·재시작 복원 테스트를 먼저 작성하고 실패 확인.
- [x] 매 거래 연결·잠금·참조 검사를 구현하고 `python3 -m unittest discover -s prototype/tests -v`로 확인.

## Task 2 — 배정·병렬 실행·조언
Files: prototype/engine.py, prototype/models.py, prototype/tools.py, prototype/tests/test_engine.py
Interface: Engine.submit(...)는 run_id 반환; Engine.process(run_id)는 독립 요원을 동시 실행하고 검증 후 종합한다. Model.call(role,stage,context)는 검증 가능한 JSON 반환.
- [x] 실제 작업 구간 중첩·세션 전환 중 보고·시뮬레이션 사실 보존·실패 전파 테스트를 작성하고 실패 확인.
- [x] 역할 설정과 Responses 요청 경로, 데모 모델, 검색·CSV·기상 도구 구현.
- [x] 요청·배정·임무·검증·최종 보고를 저장하고 전체 테스트 실행.

## Task 3 — API·입력 화면·상황판
Files: prototype/server.py, prototype/static/index.html, app.js, style.css, prototype/tests/test_http.py
- [x] HTTP 경계의 입력 검증·읽기 전용 경로·Origin 검사·세션 미존재·중복 접수 테스트를 먼저 작성.
- [x] 세션 생성·전환, 담당자 채팅·첨부·정정·시뮬레이션, 고정 세션 상황판 구현.
- [x] 클라이언트 갱신·지연 경고·입력 보존·이벤트 타임라인·실제 실행 구간 표시.
- [x] 브라우저에서 세션 생성→요청→개별 보고→최종 보고, 가정 비교, 세션 전환·상황판 확인.

## Task 4 — 검증·전달
Files: prototype/README.md, prototype/PROGRESS.md, 04 구현 현황
- [x] 전체 unittest, 실제 로컬 HTTP와 브라우저 동작 확인.
- [x] 새 관점의 코드 검토 후 중요 결함 수정.
- [x] 실행 방법·API 키 설정·구현/미검증/미구현을 기록하고 작동 화면을 연다.

## 실행 결정
- Ruling: 기존 발표와 문서의 미커밋 변경을 보존하며 새 prototype/ 아래에서만 제품 코드를 개발한다. 별도 체크아웃·커밋·배포는 하지 않는다.
- Ruling: 사용자 요청에 따라 구현을 계속한다. 추가 승인 단계 대신 기존 설계의 작은 흐름을 작동·검증한다.
- Ruling: API 키 미설정은 실제 모델 검증만 제한한다. 명시적인 데모로 저장·병렬 실행·UI를 검증하며 API 성공을 주장하지 않는다.

검증 결과와 부분 구현의 한계는 prototype/PROGRESS.md에 기록했다. 실제 모델/기상 성공을 완료로 처리하지 않는다.
