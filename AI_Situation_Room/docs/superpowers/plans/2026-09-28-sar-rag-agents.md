# SAR 요원·기록·화면 연동 구현계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 담당자가 보낸 지시에 대해 요원들이 관련 매뉴얼을 제공받고, 사용 근거를 검증·종합·확인할 수 있게 한다.

**Architecture:** 서버가 run 시작 시 검색 세대를 고정하고 배정 후 전문요원 임무별로 검색한다. 근거 스냅샷은 세션에 묶어 저장하고 검증·최종 보고에 합집합으로 전달한다. 기존 전송·수신함 승인 흐름을 재사용한다.

**Tech Stack:** 기존 Python 엔진·SQLite·HTTP API·vanilla JS. 검색 인터페이스는 [검색 계획](2026-09-28-sar-rag-search.md)을 따른다.

**Spec:** [전체 계획](2026-09-28-sar-rag.md), [기존 매뉴얼 요구](../../improvements/03-local-manuals.md).

## Global Constraints

[공통 제약](2026-09-28-sar-rag.md#global-constraints) 적용. 조회·수신만으로 작업을 만들지 않는다. 매뉴얼의 권고를 사건 사실이나 실제 출동으로 저장하지 않는다. 단순 이름 정정·장부 갱신의 빠른 경로를 유지한다.

## Review Focus

- 역할별로 다른 근거의 전달 누락(G1), 세션 간 근거 조회(G3), 부정·종료 상태의 반복 출동(G2), 검색 오류를 숨긴 정상 표시(G3), 추가 검색의 무한 반복(G4).

---

## 파일 책임

- 신규 `prototype/manual_rag/context.py`: 사건·임무 질의, 예산, 근거 결합·스냅샷 형식.
- 수정 `prototype/engine.py`: retriever 주입, run 세대 고정, 단계별 전달·오류 상태.
- 수정 `prototype/tools.py`: 기존 evidence 생성 결과에 매뉴얼 항목을 합치는 선택 인자. 기존 첨부 검색 계약 유지.
- 수정 `prototype/models.py`: 근거 사용·부족 표시 지시와 새 보고 필드. DEMO는 규칙형 표시를 유지한다.
- 수정 `prototype/store.py`: 근거·검색 기록 보존과 세션별 조회.
- 수정 `prototype/manuals.py`: 기존 키워드 출동 후보의 현재 상태 판단.
- 수정 `prototype/server.py`: 검색 설정·서비스 수명·근거 조회 API.
- 수정 `prototype/static/app.js`, `style.css`: 근거 버튼·패널·오류/부분 검색 표시.
- 신규 `prototype/tests/test_manual_engine.py`, `test_manual_http.py`, `browser_manuals.cjs`; 기존 `test_engine.py`, `test_models.py`, `test_send.cjs` 확장.

## 연결·저장 계약

- `Engine(..., manual_search=None)` 추가. `None`이면 기존 동작이다. 서버가 생성한 검색 서비스의 소유권은 서버에 두고 종료 시 한 번 닫는다.
- `context.py`: `prepare_manual_context(run: dict, session: dict, assignment: dict, searcher, *, generation: str, budget: dict) -> dict` 반환은 `evidence`, `search_record`.
- `tools.evidence_for(snapshot, query, manual_items=None)` 추가. 기존 `basic_manual`, `donghae_assets`는 유지하고 신규 ID 중복만 제거한다.
- `Store.record_manual_context(sid: str, rid: str, stage: str, role: str, search_record: dict, items: list[dict]) -> str`는 세션·run 소유권을 확인하고 `objects.kind=manual_contexts`로 본문·판본·해시·실제 전달 ID·검색 상태를 함께 저장한다.
- `Store.get_manual_context(sid: str, rid: str, context_id: str) -> dict`: 세 식별자를 모두 대조한다. 다른 세션이면 404다. run에는 `manual_context_ids`만 추가한다.
- 근거 스냅샷은 모델 호출 **전**에 저장한다. 호출 실패도 당시 입력을 재현할 수 있어야 한다. 대기열 중복 실행에는 새 기록을 중복 생성하지 않는다.
- 기존 보고 `evidence_ids` 유지. 신규 선택 필드 `evidence_links=[{claim, evidence_ids, application, limitations}]`는 매뉴얼을 사용한 제안과 근거를 연결한다. claim은 보고의 실제 제안/검토 문장과 일치해야 한다. ID 존재 검사는 유지하며 의미상 지지 여부는 답변 평가로 확인한다.
- 매 1초 snapshot에는 본문을 반복 싣지 않고 근거 ID·제목·상태·context ID만 제공한다. 상세는 별도 API로 읽는다.

### Task G1: 자동 검색·요원 간 인계·스냅샷

**Files:** `context.py`, `engine.py`, `tools.py`, `store.py`, `models.py`, `test_manual_engine.py`.

**Interfaces:** 위 계약 및 S3 `retrieve_manuals`.

- [ ] `test_role_evidence_reaches_critic_and_final`, `test_saved_context_survives_corpus_update`, `test_no_search_on_unapproved_inbox`, `test_rag_off_preserves_existing_flow` 작성. 가짜 retriever·provider로 실제 입력 배열과 DB 내용을 검사한다.
- [ ] `python3 -m unittest prototype.tests.test_manual_engine -v`로 FAIL 확인.
- [ ] run 시작 시 generation을 고정한다. 배정 단계에는 기존 짧은 기본 자료를 사용하고 검색을 위한 추가 LLM 호출은 만들지 않는다. tasks가 없는 단순 정정은 국제 검색 없이 끝내고 `not_requested`를 남긴다.
- [ ] 배정된 전문요원별 검색 입력에 최신 사건·해당 임무·승인된 지시를 사용한다. 미확인 외부 보고는 질의에 활용하더라도 미확인 출처를 유지한다. 매뉴얼은 update의 사실 근거가 될 수 없다.
- [ ] 단계 전체의 입력 예산에서 출력·시스템 지시·사건 입력을 먼저 확보한다. 초기 추가 매뉴얼 예산은 전문가별 최대 2,000, 검증·종합 합계 최대 6,000토큰을 제안한다. provider가 지원하는 실제 문맥 길이를 확인해 더 작은 값으로 제한한다. 정확한 tokenizer가 없는 클라우드 경로는 UTF-8 byte 길이를 보수적 입력 크기 추정으로 사용하고 '실제 토큰 수'라고 기록하지 않는다.
- [ ] 처음부터 전문요원 근거의 합집합이 후속 예산에 들어가도록 배분한다. 조건 묶음을 자르지 않는다. 지원할 수 없는 크기는 부분 검색으로 알리고 무근거 생성을 강행하지 않는다. 사건 자체가 입력 한도를 넘으면 기존 한도 오류 흐름을 유지한다.
- [ ] 선택 요원의 실제 전달 근거 합집합을 검증요원과 최종 상황실장에 전달한다. 검증에 새 근거를 추가했다면 최종 단계에도 전달한다. 모든 단계의 입력 ID를 검증하고 스냅샷 저장한다.
- [ ] 같은 시험 PASS 및 기존 `python3 -m unittest prototype.tests.test_engine prototype.tests.test_models prototype.tests.test_store -q` 회귀 후 변경 범위 커밋.

### Task G2: 기존 출동 후보와 최신 상태 일치

**Files:** `manuals.py`, `engine.py`, `models.py`, `test_manual_engine.py`, 기존 `test_incident.py`.

**Interfaces:** `recommended_dispatch(prompt, session)`의 반환 계약은 유지한다. 추가 helper `current_hazards(prompt: str, incident: dict) -> dict`는 위험별 `active|resolved|absent|unknown`와 원문 근거를 반환한다.

- [ ] `test_pollution_absent_does_not_recommend_cleanup`, `test_support_ended_not_redispatched`, `test_new_fire_after_extinction_is_reviewed`, `test_external_report_does_not_write_hazard_fact` 작성. 광범위한 단순 부정 단어 제거로 다른 실제 위험까지 사라지지 않는지도 검사한다.
- [ ] 시험 FAIL 확인 후 현재 장부·현재 신고·과거 경과를 구분한다. 명시적 해소·종료는 과거 키워드보다 우선하고 모호한 새 정보는 확인 질문으로 남긴다. 순수 substring 규칙만으로 현재 위험을 확정하지 않는다.
- [ ] 현재 출동·도착·지원 종료 상태와 중복되는 후보를 제거한다. 모델·규칙 제안이 충돌하면 임의 결합하지 말고 최종 검토에서 충돌과 확인 필요를 표시한다. 실제 장부 갱신은 기존 사용자 보고 경로만 사용한다.
- [ ] `python3 -m unittest prototype.tests.test_manual_engine prototype.tests.test_incident prototype.tests.test_engine -q` PASS 확인 후 커밋한다. 자연어 모든 부정 표현을 해결했다고 주장하지 않는다.

### Task G3: 근거 API·화면·통합 수용 시험

**Files:** `server.py`, `store.py`, `static/app.js`, `static/style.css`, `test_manual_http.py`, `browser_manuals.cjs`, 관련 구현 문서.

**Interfaces:** `GET /api/sessions/{sid}/runs/{rid}/manual-contexts/{context_id}` 읽기 API. 기존 Host/Origin 검사 적용. 원문 링크가 필요하면 `GET /api/manual-sources/{source_id}/pdf`를 추가하고 공개 출처 등록부의 ID만 허용한다. 임의 파일 경로·내부 PDF·디렉터리 탐색을 허용하지 않는다.

- [ ] `test_context_is_scoped_to_session_and_run`, `test_context_get_does_not_execute`, `test_source_path_traversal_rejected`, `test_snapshot_omits_large_bodies` 작성. 임시 SQLite·자동 할당 포트로 HTTP 시험 FAIL 확인.
- [ ] 기존 근거 영역과 보고의 사용 근거를 확장한다. 문서명·판본·PDF쪽·한국어 요약/원문·적용 제한·초안 상태를 보여준다. `pdf_pages`와 인쇄 쪽번호를 혼동하지 않는다.
- [ ] “전달된 근거”와 “보고가 인용한 근거”를 구별한다. `partial`, `no_match`, `unavailable/error`, `degraded`는 짧은 한국어 설명으로 표시한다. 벡터 유사도와 모델 설정을 일반 화면에 노출하지 않는다.
- [ ] 모든 문서·요약은 텍스트로 escape한다. 외부 URL은 검증된 http(s)만 링크로 만들고, PDF에는 등록된 로컬 경로만 사용한다. 모달은 제목·닫기·Escape·포커스 복귀를 지원한다.
- [ ] `python3 -m unittest discover -s prototype/tests -q`, `node --check prototype/static/app.js`, `node prototype/tests/test_send.cjs` 실행. HTTP 포트 권한과 JS 실행 환경은 README를 따른다.
- [ ] `node prototype/tests/browser_manuals.cjs` 및 기존 `browser_inbox.cjs`를 Playwright 준비 환경에서 실행한다. 임시 DB로 출처 열기·사건 전환·한글 입력/초안 보존·중복 승인·삭제 보호·대형화면 복귀를 확인한다.
- [ ] 별도 LIVE 시험에서 동일 입력의 기존/hybrid 보고를 비교한다. 20개 국제 행동 사례에 대해 제공되지 않은 ID 0건, 확인한 사례에서 출처가 지지하지 않는 단정 0건, 자동 사실 승격 0건을 요구한다. 판정불가도 완료 처리하지 않는다. 자동 ID 검사와 사람이 원문을 대조한 의미 검사를 별도로 기록한다.
- [ ] 검색 p95, 최초 배정, 첫 요원 보고, 전체 완료 시간과 실패율을 기록한다. 근거 자료 추가가 배정 지연을 늘렸는지 확인한다. 테스트 fixture의 DEMO 결과로 LIVE 정확도를 주장하지 않는다.
- [ ] 13·PROGRESS·README와 기존 기능별 명세를 갱신한다. 새 `docs/implementation/24-local-manual-rag.md`에 실제 계약·설정·복구·검증을 적고 커밋한다.

### Task G4: 근거 부족 시 제한된 추가 검색 — M2

**Files:** `models.py`, `engine.py`, `context.py`, `test_manual_engine.py`.

**Interfaces:** 전문요원 report의 선택 필드 `evidence_requests=[{query, reason}]`, 최대 1개. 요청은 사실이나 실행 명령이 아니다.

- [ ] `test_second_retrieval_is_bounded`, `test_second_query_keeps_scope_and_generation`, `test_missing_evidence_is_reported_after_retry` 작성. 반복 요청·빈 요청·장문 요청·검색 실패를 포함한다.
- [ ] FAIL 확인 후 초안 보고에 구체적 자료 부족 요청이 있으면 서버가 같은 정책·세대·예산으로 한 번 추가 검색한다. 새 근거가 없으면 같은 모델을 반복 호출하지 않는다.
- [ ] 새 근거가 있을 때만 해당 요원을 한 번 재호출한다. 전문요원당 총 report 호출 상한은 2회이며 중간 보고는 최종처럼 표시하지 않는다. 추가 검색은 다른 요원의 독립 검토를 막지 않는다.
- [ ] 추가 호출에도 부족하면 불확실성과 확인 질문을 최종 보고에 남긴다. 검증요원·상황실장의 재귀적 검색 루프는 첫 버전에 넣지 않는다.
- [ ] G1~G3 회귀·추가 지연을 확인한 뒤 활성화한다. 상한·실패 기록·추가 근거 인계를 문서화하고 커밋한다.
