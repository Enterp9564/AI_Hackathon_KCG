# SAR 로컬 하이브리드 검색 구현계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 인터넷 없이 사건·임무에 맞는 자료를 검색하고 근거 부족·오류를 구분한다.

**Architecture:** 로컬 임베딩으로 Qdrant 후보를 찾고 BM25 후보와 RRF로 결합한다. 검토 상태·판본·사용 범위를 먼저 제한하고 필수 조건을 복원한다. 인덱스는 세대별로 생성하며 실행 중에는 변경하지 않는다.

**Tech Stack:** Python, Qdrant client 로컬 모드, Sentence Transformers, `intfloat/multilingual-e5-small` 평가 후보, `rank-bm25` 후보. 설치된 환경에서 검증 후 정확한 버전을 잠근다.

**Spec:** [전체 계획](2026-09-28-sar-rag.md), [자료 계약](2026-09-28-sar-rag-corpus.md), [기존 설계](../../improvements/03-local-manuals.md).

## Global Constraints

[공통 제약](2026-09-28-sar-rag.md#global-constraints) 적용. 런타임 모델 다운로드·외부 임베딩 API를 사용하지 않는다. 관련도 점수를 정확도 확률로 표시하지 않는다.

## Review Focus

- 한국어↔영어·부정 표현·두 글자 용어(S3), 모델/색인 판본 불일치(S2), 무관한 질문(S4), 재시작 후 결과 변동(S2), 조건 잘림(S3)을 검증한다.

---

## 파일과 외부 자료

- 신규 `prototype/manual_rag/embedding.py`: 로컬 모델 경로·tokenizer·벡터 생성.
- 신규 `prototype/manual_rag/index.py`: Qdrant 소유 작업자, 인덱스 세대 생성·검증·활성화.
- 신규 `prototype/manual_rag/retrieval.py`: 질의 구성·BM25·RRF·예산·반환 계약.
- 신규 `prototype/manual_rag/evaluate.py`, `prototype/manuals/library/evaluation/`: 평가 실행·동의어·개발/보류 사례. 기존 평가 초안은 보존.
- 신규 `prototype/requirements-rag.in`, `prototype/requirements-rag.lock`: 직접 의존성과 대상 환경에서 확인한 고정 버전.
- 신규 `prototype/tests/test_manual_search.py`, `prototype/tests/test_manual_index.py`.
- 수정 `prototype/.gitignore`: 모델·인덱스·임시 평가 산출물 제외. 기존 제외 목록 유지.
- 런타임 기본 위치 `prototype/runtime/manual-rag/` 아래 `models/`, `indexes/<generation>/`, `evaluations/`. 설치·생성은 명시적 준비 명령에서만 한다.

참고: [Qdrant 로컬 저장](https://github.com/qdrant/qdrant-client#local-mode), [RRF 결합 설명](https://qdrant.tech/documentation/search-tuning/hybrid-search/), [E5 모델 카드](https://huggingface.co/intfloat/multilingual-e5-small/blob/main/README.md). 모델 카드의 입력 접두어·정규화·길이 조건을 고정한 revision과 함께 확인한다.

## 검색 반환 계약

`retrieve_manuals(query: str, incident: dict, role: str, assignment: str, *, generation: str, mode: str, target: str, budget_tokens: int) -> SearchResult`.

- `mode=lexical|hybrid`; `target=cloud|local`; 사건 입력은 호출 세션의 현재 장부와 승인된 지시에서만 만든다.
- `SearchResult`: `status`, `reason`, `generation`, `method`, `items`, `omitted_ids`, `latency_ms`, `warnings`.
- `status=ok|partial|no_match|unavailable|error`. `partial`은 조건 묶음 또는 예산 때문에 필요한 후보 일부를 전달하지 못한 경우다. `ok`도 지침의 완전성이나 충분한 답변을 보증하지 않는다.
- `items[]`: `id`, `chunk_id`, `section_id`, `document_id`, `title`, `content`, `source_version`, `source_url`, `locator`, `pdf_pages`, `review_status`, `limitations`, `content_sha256`, `scope`, `external_use`, `retrieval_rank`.
- `id`는 이번 실행에 제공한 완전한 근거 묶음의 내용·판본에 대한 해시를 포함한다. `content`에 본문과 필요한 조건을 넣고, 기존 `evidence` 배열에 추가 가능한 구조로 반환한다.
- 정책 필터는 양쪽 검색 전에 적용한다. 현재 공개 corpus만 허용하며 `target=cloud`에서 `external_use=deny`는 반드시 제외한다. 보안 필터 실패 시 검색을 중단한다.
- 단순 역할 태그는 순위 동률 해소에 사용하며 관련 조항을 강제로 배제하지 않는다.

### Task S1: 로컬 임베딩과 재현 가능한 준비 환경

**Files:** `embedding.py`, `requirements-rag.*`, `test_manual_search.py`, `prototype/.gitignore`.

**Interfaces:** `LocalEmbedder(model_dir: Path)`; `encode_queries(texts: list[str]) -> list[list[float]]`; `encode_passages(texts: list[str]) -> list[list[float]]`; `token_count(text: str) -> int`.

- [ ] `test_query_passage_prefix_and_normalization`, `test_missing_model_does_not_download`, `test_embedding_input_not_truncated`를 가짜 tokenizer/encoder로 작성한다. 누락 모델은 준비 필요 오류, 긴 입력은 분할 요구 오류여야 한다.
- [ ] `python3 -m unittest prototype.tests.test_manual_search -v`로 FAIL 확인.
- [ ] 모델 로컬 경로만 받아 `local_files_only`로 연다. E5 후보는 query/passage 접두어와 정규화 정책을 모델 카드대로 적용하고 벡터 차원·revision을 기록한다. 입력 한도 초과를 조용히 자르지 않는다.
- [ ] 별도 가상환경에 후보 패키지와 모델을 준비해 CPU 설치·한국어 입력을 확인한다. 모델의 라이선스·revision·파일 해시·토큰 한도를 기록하고 테스트한 패키지 버전을 잠근다. 모델 파일은 Git에 넣지 않는다.
- [ ] 단위 시험 PASS 후 네트워크 차단 상태에서 실제 임베딩을 생성한다. 모형 encoder 단위 시험과 실제 모델 결과를 따로 기록하고 커밋한다.

### Task S2: 인덱스 생성·세대 고정·복구

**Files:** `index.py`, `test_manual_index.py`.

**Interfaces:** `build_index(corpus_dir: Path, embedder: LocalEmbedder, output_dir: Path) -> dict`; `open_index(generation_dir: Path) -> ManualIndex`; `ManualIndex.search(vector, filters, limit) -> list[dict]`; `ManualIndex.close() -> None`.

- [ ] `test_restart_preserves_results`, `test_build_failure_keeps_active_generation`, `test_model_revision_mismatch_rejected`, `test_simultaneous_queries_use_single_owner` 작성. 인덱스 생성 중 프로세스 종료·모델 변경·조회 6개 동시 요청을 포함한다.
- [ ] `python3 -m unittest prototype.tests.test_manual_index -v`로 FAIL 확인.
- [ ] 한 작업자에서 Qdrant를 만들고 모든 로컬 접근을 그 작업자로 보낸다. 다중 프로세스의 동일 경로 쓰기를 허용하지 않는다. 앱 실행 중 재색인은 별도 경로에만 한다.
- [ ] 세대 manifest에 corpus/모델/tokenizer/retrieval 설정 해시, 차원, 정규화, 패키지 버전, 문서 수를 넣는다. 안정 UUID로 Qdrant point ID를 만들고 원래 구절 ID는 payload에 보존한다.
- [ ] 새 세대가 검증되면 활성 경로 설정을 원자적으로 바꾼다. 실제 앱은 재시작 때 읽고 각 run에 generation을 고정한다. 깨진 새 세대는 활성화하지 않는다.
- [ ] 시험 PASS 후 두 번 빌드·재시작·실패 주입 결과를 기록해 커밋한다. 옛 인덱스와 사용자 자료를 자동 삭제하지 않는다.

### Task S3: 의미·키워드 검색과 문맥 예산

**Files:** `retrieval.py`, `evaluation/synonyms.json`, `test_manual_search.py`.

**Interfaces:** 위 `retrieve_manuals`; `build_queries(query: str, incident: dict, assignment: str) -> list[str]`; `expand_evidence(chunk_ids: list[str], budget_tokens: int) -> dict`(`items`, `omitted_ids`).

- [ ] `test_two_character_terms_and_paraphrase`, `test_compound_incident_covers_both_topics`, `test_no_current_danger_inferred_from_negation`, `test_required_conditions_not_cut`, `test_scope_filter_applies_to_both_rankings` 작성. 무관한 기본 채움은 금지한다.
- [ ] S1 시험 명령으로 FAIL 확인.
- [ ] Unicode 정규화·원문 단어·검토한 한국어/영어 동의어로 BM25 입력을 만든다. 부정·종료 표현은 질의와 사건에 남긴다. 검색기가 위험 사실을 새로 생성하지 않는다.
- [ ] 최신 지시+현재 사건+임무 질의를 만들고, 복합사고는 최대 3개 하위 질의로 나눈다. 한 질의는 임베딩 한도 이내여야 한다. 사건 전체를 끝에서 잘라 맞추지 말고 필드별로 구성한다.
- [ ] 질의마다 dense·BM25 후보를 각각 최대 12개 찾는다. BM25 0점은 제외한다. 동일 구절의 원문/한국어 표현은 합치고 RRF `1/(60+rank)`를 사용한다. 최종 검색 조각은 최대 6개이며 절별 중복을 제한한다. 이 값들은 초기 제안이며 S4에서 고정한다.
- [ ] 점수 임계값은 개발 세트에서 정하고 설정에 저장한다. 보류 세트로 튜닝하지 않는다. 순위 점수만으로 답변 가능성을 판단하지 않는다.
- [ ] 검색 조각의 필수 조건·예외를 복원한 뒤 실제 생성 모델의 예산으로 전체 묶음을 넣거나 제외한다. 예산 초과는 `partial`/`omitted_ids`로 보고한다. 임베딩 tokenizer와 생성 모델 tokenizer를 구분한다.
- [ ] 단위 시험 PASS 후 실제 임베딩으로 같은 사례를 확인하고 커밋한다.

### Task S4: 검색 품질·오프라인·지연 평가

**Files:** `evaluate.py`, `evaluation/retrieval-dev.json`, `retrieval-holdout.json`, `behavior.json`, `test_manual_search.py`.

**Interfaces:** `evaluate_search(cases: list[dict], searcher, mode: str) -> dict`; CLI `python3 -m prototype.manual_rag.evaluate --cases <path> --mode lexical|hybrid --output <path>`.

- [ ] 기존 국제 20개를 그대로 보존하고 검색용 정답과 행동 검사로 분리한다. '자료가 없다'와 '정책상 할 수 없다'를 같은 검색 정답으로 취급하지 않는다. 개발·보류 각 12개 이상을 작성하고 각 세트에 무관 질문 3개 이상을 포함한다.
- [ ] `test_evaluation_reports_misses_and_no_match` 작성: 문서/절 recall@6, 무관 질문 오반환 수, 필수 조건 누락, cold/warm 지연, 실패·degraded를 별도 집계한다. 지표 계산 시험 FAIL 확인 후 구현하고 PASS 확인.
- [ ] 같은 모델·자료·장비로 lexical과 hybrid를 비교한다. 보류 정답은 검색 결과를 보기 전에 고정한다. 첫 목표는 관련 질문의 평균 recall@6 ≥ 0.90, 복합사고 정답 분야 모두 검색, 보류 무관 질문 오반환 0건이다. 소수 사례 통과는 일반 정확도 보장이 아니다.
- [ ] 네트워크를 차단하고 실제 임베딩·재시작 후 검색한다. 모델 없음·손상 색인·시간 초과는 `unavailable|error`이고 빈 정상 결과가 아니어야 한다.
- [ ] 목표 장비에서 warm 검색 p95 2초 이내를 초기 목표로 측정한다. cold 시작·동시 요청 대기·요원 전체 시간은 별도 기록한다. 초과 시 최적화하거나 명시적 lexical 모드로 운영한다.
- [ ] 결과가 기준 미달이면 실패 사례·원인과 변경 설정을 남기고 새 보류 사례로 재평가한다. 결과 파일·문서·버전 잠금을 검토해 커밋한다.

## 실패 시 동작

- 벡터 모델/색인 가용성 오류 시 같은 검토 corpus의 lexical 검색을 시도할 수 있지만 `warnings`에 `degraded`와 원인을 기록한다.
- corpus 무결성·권한 검사 오류는 lexical로도 우회하지 않는다. 기존 기본 매뉴얼 경로만 남기고 국제 자료 검색 불가를 알린다.
- 검색 결과·모델 생성 결과를 다른 사건 캐시에 섞지 않는다. 최초 버전에서는 사건 질의 캐시를 추가하지 않는다.
