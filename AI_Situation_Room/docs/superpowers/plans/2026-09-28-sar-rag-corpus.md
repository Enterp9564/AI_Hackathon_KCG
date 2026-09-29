# SAR 원문 파싱·정제 구현계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 원문 위치와 조건·예외를 잃지 않는 검색용 자료를 만든다.

**Architecture:** 기존 원본과 페이지 텍스트를 보존하고, 구조화한 절·검색 조각·처리 범위를 별도로 생성한다. 자동 추출 결과와 확인된 검색 대상은 분리한다.

**Tech Stack:** Python, JSONL, pypdf, 임베딩 후보의 로컬 tokenizer.

**Spec:** [요구·설계](../../improvements/03-local-manuals.md), [전체 계획](2026-09-28-sar-rag.md).

## Global Constraints

[전체 계획의 Global Constraints](2026-09-28-sar-rag.md#global-constraints)를 적용한다. 원본·기존 요약을 덮어쓰지 않고 신규 산출물로 만든다. 한국어 작성 요약과 원문 인용을 구분한다.

## Review Focus

- 표의 열 순서·각주 누락, 페이지 경계에서 조건 분리, 잘못된 절 제목, 한국어 요약의 과도한 단정, 중복 ID를 C1~C3에서 검증한다.

---

## 파일 책임

- 신규 `prototype/manual_rag/schema.py`: 자료 계약 검증·ID·해시.
- 신규 `prototype/manual_rag/corpus.py`: 로컬 자료 읽기·검토 상태 필터·원문 연결.
- 신규 `prototype/manual_rag/prepare.py`: 수동 실행 CLI. 패키지 `__init__.py` 포함.
- 신규 `prototype/manuals/library/processed/`: `sections.jsonl`, `chunks.jsonl`, `coverage.json`, `review-overrides.json`, `README.md`.
- 신규 `prototype/tests/test_manual_corpus.py`, `prototype/tests/fixtures/manual_rag/`: 작게 작성한 가상 문서와 경계 사례.
- 수정 `prototype/manuals/library/manifest.json`: 새 정제 파일만 추가하고 원본 해시 유지.

## 공통 데이터 계약

`Section` 필수 필드:

- `section_id`, `source_id`, `source_version`, `original_sha256`, `heading_path`, `locator`, `pdf_pages`(1부터 시작).
- `text_original`, `summary_ko`(없으면 빈 문자열), `summary_kind=authored_summary|none`, `limitations`, `related_section_ids`.
- `content_kind=procedure|narrative|table|figure|front_matter`, `structure_status=verified|needs_review|excluded`.
- `review_status=draft_needs_domain_review|domain_reviewed`, `operational_authority=false`.
- `scope=shared_public_reference`, `external_use=allow`, `source_url`. 이 값은 관리자가 출처 정책으로 부여하며 PDF 내용에서 권한을 추론하지 않는다.

`Chunk`는 `section_id`와 출처 필드를 참조하며 `chunk_id`, `document_id`, `title`, `source_kind`, `content_sha256`, `text_original`, `summary_ko`, `tags`, `roles`, `required_section_ids`를 가진다. 원문·연결된 필수 조건이 모두 존재할 때만 등록한다. 검색 등록 조건은 구조 확인 완료이며, 전문 검토 미완료 상태는 전달·표시에서 유지한다. `document_id`는 기존 평가 문서 ID와 대응시키고 원문 확대 시 매핑을 등록한다.

기존 14개 요약은 `content_kind=authored_summary`인 호환 레코드로 변환하고 기존 ID를 `legacy_id`에 보존한다. 원문 전체를 담았다고 표시하지 않는다. 신규 ID는 `source_id:판본:절:조각번호:본문해시앞12자`이며 내용 변경 시 바뀐다. 원문 추출과 번역 수정은 각각 해시에 반영한다.

### Task C1: 자료 계약과 기존 14개 변환

**Files:** `schema.py`, `corpus.py`, `prepare.py`, `test_manual_corpus.py`.

**Interfaces:** `validate_chunk(record: dict, sections: dict) -> None`; `load_corpus(path: Path) -> list[dict]`; `convert_curated(source_dir: Path, output_dir: Path) -> dict`(개수·오류 목록).

- [ ] `test_curated_migration_preserves_14_sources` 작성: 14개, 기존 ID 보존, 원문 페이지·적용 제한·초안 표시 유지. `test_invalid_source_page_or_duplicate_id_rejected`는 범위 밖 페이지·중복 ID·누락 조건을 거절한다.
- [ ] `python3 -m unittest prototype.tests.test_manual_corpus -v` 실행해 신규 기능 부재로 실패함을 확인한다.
- [ ] 위 인터페이스 구현. 무결성 오류가 하나라도 있으면 완성 산출물을 활성화하지 않고 오류 보고만 남긴다. 임시 폴더에서 성공한 뒤 목적 폴더로 교체한다.
- [ ] 같은 명령으로 PASS 확인. 원본·기존 14개 파일의 전후 해시가 동일한지 확인한다.
- [ ] 자료 계약·테스트·정제 산출물을 변경 범위만 검토해 커밋한다.

### Task C2: 절 구조와 검색 조각 준비

**Files:** `prepare.py`, `corpus.py`, `processed/review-overrides.json`, `test_manual_corpus.py`.

**Interfaces:** `extract_sections(source: dict, pages: list[dict], overrides: dict) -> list[dict]`; `split_section(section: dict, tokenizer, max_tokens: int=480) -> list[dict]`.

- [ ] `test_cross_page_condition_keeps_reference`, `test_table_without_review_is_excluded`, `test_header_cleanup_keeps_body_and_page`, `test_overlong_clause_is_not_silently_truncated` 작성. 페이지 경계·반복 머리말·表 안의 숫자·長文으로 각각 누락 여부를 단언한다.
- [ ] C1과 같은 명령으로 FAIL 확인.
- [ ] 기존 페이지 추출본을 입력으로 문서별 제목·조항 규칙을 적용한다. 판단이 불명확하면 `needs_review`로 남긴다. `review-overrides.json`에 원본 해시, 페이지, 절 경계와 수정 이유를 저장한다.
- [ ] 긴 절은 문장·항목 경계에서 나누고 상위 절·필수 조건을 연결한다. 임베딩 입력은 제목·접두어·요약을 포함한 tokenizer 결과가 480토큰 이내여야 한다. 분할 불가능한 표·절은 자동 자르지 않고 보류한다.
- [ ] 검색에는 짧은 조각을 쓰되 요원 전달에는 필요한 조건·예외를 함께 복원한다. 요약에 원문에 없는 현장 수치·기관 권한을 추가하지 않는다.
- [ ] 시험 PASS와 PDF 대조 결과를 기록한다. 잘못 파싱된 페이지를 확인 완료로 승격하지 않는다. 변경 범위 커밋.

### Task C3: 전체 561쪽 처리 상태와 핵심 분야 확대

**Files:** `processed/*`, `prepare.py`, `test_manual_corpus.py`, 기존 `library/manifest.json`.

**Interfaces:** `audit_coverage(sources: list[dict], sections: list[dict]) -> dict`. 각 원본 페이지에 `indexed|needs_review|excluded` 및 사유·연결 절 목록을 반환한다. 페이지에 미검토 내용이 남으면 `needs_review`로 유지한다.

- [ ] `test_coverage_accounts_for_all_pages` 작성: 6개 문서·561개 페이지의 누락·중복·범위 오류를 거절하고 표지·목차 제외 사유를 요구한다.
- [ ] 시험 FAIL 확인 후 전체 원문을 처리한다. 모든 페이지를 검색에 넣는 것이 목표가 아니라 처리 상태를 빠짐없이 기록하는 것이 목표다.
- [ ] 접수·수색 계획·구조 자원·다수 인명 분야에서 우선 수록할 절과 필수 참조 절을 원본과 대조한다. 페이지·절·부정/조건/예외·숫자·주체를 확인하고 검사자·시각·판본을 기록한다.
- [ ] 각 수록 분야의 정상 사례와 근거 부족 사례를 검색 평가 세트에 추가한다. 기존 기대 답변을 새 검색 결과에 맞춰 바꾸지 않는다.
- [ ] `python3 -m prototype.manual_rag.prepare --source prototype/manuals/library/international --output prototype/manuals/library/processed --audit` 실행. 이 명령은 본 작업에서 새로 구현할 CLI이며 현재는 존재하지 않는다.
- [ ] 성공 산출물·해시·보류 목록·분야별 수록 범위를 기록하고 시험 PASS 후 커밋한다. 원문 전체 전문가 검토 완료로 표현하지 않는다.

## 완료 기준

- 561쪽 모두의 처리 상태가 추적되고, 첫 출시의 14개 요약과 이후 추가한 절의 범위를 구분한다.
- 검색에 사용한 모든 문장은 원문 위치 또는 HAEON 작성 요약으로 추적된다.
- 구조 검토 미완료 표·그림·절은 자동 조언 근거에서 제외된다.
- 다음 단계는 [검색 구현](2026-09-28-sar-rag-search.md)이다.
