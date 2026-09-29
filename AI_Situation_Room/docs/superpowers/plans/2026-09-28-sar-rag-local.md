# SAR 로컬 LLM 전환·운영 검증 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 같은 검색 자료와 근거 계약을 유지하면서 인터넷 없이 요원 검토를 실행한다.

**Architecture:** 검색·임베딩과 생성 모델을 분리한다. 기존 `respond(role, stage, context) -> (result, metadata)` 계약을 구현하는 로컬 provider를 추가한다. 공급자 선택과 문맥 예산은 서버 설정으로 관리한다.

**Tech Stack:** 기존 Python 엔진·SQLite·로컬 RAG. 생성 모델·추론 런타임·양자화는 L1에서 대상 장비 측정 후 선정한다.

**Spec:** [전체 계획](2026-09-28-sar-rag.md), [요원 연동](2026-09-28-sar-rag-agents.md), [로컬화 요구](../../improvements/03-local-manuals.md).

## Global Constraints

[공통 제약](2026-09-28-sar-rag.md#global-constraints) 적용. 실제 모델 오류를 DEMO 성공으로 바꾸지 않는다. 인터넷 연결만으로 클라우드로 자동 전환하지 않는다. 장비·모델이 미정이므로 성능 동등성을 보장하지 않는다.

## Review Focus

- 실제 tokenizer와 예산 불일치, JSON 형식 오류, 동시 요청의 메모리 부족, 로컬 오류 후 외부 API 자동 호출, DEMO를 실제 로컬 추론으로 오인하는 표시를 L1~L2에서 검사한다.

---

## 선행 조건과 파일

- M1의 검색·근거 표시·회귀 검증을 먼저 완료한다.
- 대상 PC의 OS/CPU/RAM/GPU·VRAM, 허용 저장공간, 가용 시간과 목표 모델을 확인한다. 필요한 값만 기록하고 전체 환경변수·장비 식별자를 수집하지 않는다.
- 신규 `prototype/local_model.py`: 선택한 런타임의 실제 요청/응답 어댑터.
- 신규 `prototype/tests/test_local_model.py`, `prototype/scenarios/manual-rag-local-evaluation.md`.
- 수정 `prototype/models.py`, `engine.py`, `server.py`, `static/app.js`: provider 선택·능력 정보·실행 표시·사용량 기록. 클라우드 기존 기본값은 별도 결정 없이 변경하지 않는다.

### Task L1: 장비·후보 모델 평가와 선택 기록

**Files:** `scenarios/manual-rag-local-evaluation.md`, 향후 선택 모델의 로컬 설정(키 제외).

**Interfaces:** provider 설정 `{provider, model_id, endpoint, context_tokens, output_tokens, max_parallel, tokenizer_revision, supports_json}`. endpoint는 기본 loopback이며 임의 외부 주소로 원문을 전송하지 않는다.

- [ ] 장비 정보를 확인한 뒤 설치 가능한 후보 생성 모델 최대 2개를 고른다. 라이선스·한국어·문맥 길이·JSON 출력·런타임 호환성을 공식 문서로 확인한다. 이 단계 전 특정 생성 모델을 설치하거나 큰 파일을 다운로드하지 않는다.
- [ ] 저장공간·메모리 예산 안에서 후보를 준비하고 같은 공개 매뉴얼 입력으로 측정한다. 클라우드 API 없이 실제 요원 응답을 생성한다.
- [ ] JSON 유효성, 근거 ID 존재, 근거 없는 단정, 질문의 적절성, 최초 출력·완료 시간, 최대 RAM/VRAM을 기록한다. 모델 시작 시간과 warm 추론을 분리한다.
- [ ] 동시 호출 1개·2개에서 메모리·완료 시간을 비교하고 가능한 병렬 수를 정한다. 3개 요원 병렬 지원을 미리 가정하지 않는다. 순차 실행만 가능한 장비라면 현재 '실제 병렬' 요구를 충족하지 못함을 명시하고 장비/모델 변경 또는 요구 조정을 사용자에게 제시한다.
- [ ] 후보·양자화·runtime 버전·tokenizer·예산·병렬 수를 고정한다. 수용 사례에서 유효한 결과를 만들지 못하면 로컬 전환을 보류하고 실패 이유를 남긴다. 설정 값은 L2의 구체 구현 입력이 된다.

### Task L2: 로컬 provider·완전 오프라인 수용 시험

**Files:** `local_model.py`, `models.py`, `engine.py`, `server.py`, `test_local_model.py`, `static/app.js`.

**Interfaces:** `LocalModel.respond(role: str, stage: str, context: dict) -> tuple[dict, dict]`; `count_tokens(context: dict) -> int`; `capabilities() -> dict`(L1 설정). 기존 Responses provider도 같은 능력 정보의 기본값을 제공하도록 정리한다.

- [ ] `test_local_request_preserves_role_and_evidence`, `test_invalid_json_or_timeout_fails_explicitly`, `test_cloud_is_not_called_on_local_error`, `test_context_budget_reserves_output`, `test_actual_provider_metadata_saved` 작성. 가짜 HTTP 응답으로 FAIL 확인한다.
- [ ] L1의 실제 runtime 프로토콜에 맞춘 어댑터를 구현한다. timeout·중단·형식 오류·불완전 출력은 모델 실패로 기록하고 기존 엔진 검증을 통과해야 보고로 저장한다.
- [ ] `--model-provider cloud|local` 설정과 로컬 endpoint 설정을 추가한다. DEMO는 여전히 별도 규칙 모드다. UI는 LIVE/DEMO를 유지하며 실제 실행 위치는 '클라우드 실행/로컬 실행'으로 구분한다. 모델명·추론 수준은 일반 화면에 노출하지 않는다.
- [ ] `/api/config`의 `live_available`은 선택 provider의 준비 상태로 판단하게 수정한다. 로컬 provider에 클라우드 API 키를 요구하지 않고, 미준비 모델은 설정 필요로 표시한다. 기존 세션의 실행 방식이 설정 변경으로 조용히 바뀌지 않도록 각 run에 provider 설정을 고정한다.
- [ ] 호출 기록은 하드코딩된 클라우드 MODEL 대신 실제 provider/model을 기록한다. 모델별 지원하지 않는 medium 등 설정을 보냈다고 꾸미지 않는다. 기존 클라우드 설정의 동작은 유지한다.
- [ ] `python3 -m unittest prototype.tests.test_local_model prototype.tests.test_manual_engine prototype.tests.test_models -v` PASS 확인.
- [ ] 외부 네트워크 차단 후 새 프로세스에서 임베딩·검색·요원 추론·PDF 근거 열기까지 수행한다. 기상·일반 웹 검색은 오프라인 상태를 알리고 오래된 자료를 현재 관측으로 표시하지 않는다.
- [ ] 같은 공개 사건 세트로 클라우드와 로컬의 보고를 비교한다. 부정·정정·복합사고·근거 없음·긴 대화·동시 세션·추가 검색 상한을 포함한다. 회귀 기준은 G3와 같고, 속도 목표는 L1에서 사용자 운영 조건에 맞게 확정한 값을 쓴다.
- [ ] 전체 단위·HTTP·브라우저 회귀 후 모델 준비·재시작·오류·복구 절차를 README와 13·PROGRESS에 기록하고 커밋한다. 실제 실패·재시험 내역을 남긴다.

## 후속 확장 경계

- 내부 매뉴얼은 별도 반입·검토·권한 정책을 거쳐야 한다. 검색 필터와 모델 호출 직전의 전송 정책을 모두 검증한다.
- 외부 프로젝트는 기존 MCP 승인형 보고 경로로 연동한다. 벡터 DB를 핫스팟에 직접 공개하지 않는다.
- 대응 기록에서 매뉴얼 초안을 만드는 기능은 이번 범위가 아니다. 사건 기록을 자동으로 공통 corpus에 추가하지 않는다.
- 원문 전체의 계산·의료·장비 운용을 검증하는 작업은 별도 전문 검토이며, RAG 검색 성공으로 대체하지 않는다.
