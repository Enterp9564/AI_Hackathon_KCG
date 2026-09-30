# 24. 공개 국제 SAR 로컬 검색·근거 연동

> 2026-09-29 · M1 시험 기능. 기본값 `off`. 한국어 작성 요약 14개를 사용하며 원문 전체 자동 파싱·전문 운용 검토·로컬 생성 모델은 포함하지 않는다.

## 1. 사용자 흐름

담당자가 지시를 보내면 기존 상황실장 배정이 먼저 실행된다. 전문요원이 배정된 경우에만 현재 지시·사건 조건으로 국제 SAR 자료를 검색한다. 각 요원의 입력에 본문·출처·PDF 페이지·적용 제한을 추가하고, 검증요원과 최종 상황실장에 실제 전달 근거의 합집합을 넘긴다.

MCP 수신함의 접수만으로 검색하거나 요원을 실행하지 않는다. 기존 Link-One 전용 연결/갱신/재분석 경로는 그대로 유지하며 그 경로에서 이미 생성한 run의 검토에 검색을 적용한다. 단순 장부 정정처럼 전문요원이 배정되지 않는 요청에는 `not_requested`를 남긴다.

보고 상세의 ‘국제 SAR 매뉴얼’ 버튼으로 실행 당시 저장된 한국어 요약·출처·페이지·제한을 연다. ‘전달된 근거’는 모델이 실제로 인용하거나 정확하게 적용했다는 증거와 구분한다. DEMO는 기존 규칙형 보고이며 검색 입력 전달·저장·화면 시험에 사용한다.

## 2. 파일 책임

- `prototype/manual_rag/corpus.py`: 공개 corpus를 읽고 원본 PDF/요약 해시, 페이지, 중복 ID, 공개 범위·초안 상태를 검사한다. 자료를 메모리에 동결한다.
- `embedding.py`: 명시적 모델 다운로드와 `local_files_only` CPU 임베딩. 실행 중 다운로드하지 않는다.
- `index.py`: 세대별 Qdrant 생성·모델/자료 지문 검사·영속 검색. 기존 인덱스 폴더를 덮어쓰지 않는다.
- `retrieval.py`: 한국어·영어 검색 용어, BM25와 벡터 검색, RRF 결합·입력 예산·상태 반환.
- `context.py`: 검색 실패 정리·근거 합집합·입력 한도.
- `prepare.py`, `evaluate.py`: 명시적 준비·오프라인 검색 평가 CLI.
- `engine.py`, `store.py`: 근거 입력 전달·실행 당시 스냅샷·세션별 조회.
- `static/manuals.js`: 출처 상세·HTML escape·HTTPS 출처 링크·세션 변경 중 오래된 응답 무시.

## 3. 설정과 설치

기존 실행은 그대로 `python3 -m prototype.server --port 8860`이다. 국제 검색은 꺼져 있고 기본 매뉴얼과 기존 첨부 경로를 사용한다.

추가 패키지 없이 키워드 검색을 시험하려면 프로젝트 루트에서:

```bash
python3 -m prototype.server --manual-search lexical --port 8860
```

벡터 검색 준비는 별도 가상환경에서 실행한다. 처음 한 번의 패키지·모델 다운로드에는 인터넷이 필요하다. 기존 사용자 runtime을 삭제하지 않는다.

2026-09-29 현재 작업 장비에는 아래 경로의 venv·모델·인덱스를 준비하고 오프라인 평가를 통과했다. 이 장비에서는 마지막 서버 명령으로 시험할 수 있다. 새 장비에서는 준비 명령부터 실행한다.

```bash
python3 -m venv prototype/runtime/manual-rag/venv
prototype/runtime/manual-rag/venv/bin/python -m pip install -r prototype/requirements-rag.lock
prototype/runtime/manual-rag/venv/bin/python -m prototype.manual_rag.prepare audit
prototype/runtime/manual-rag/venv/bin/python -m prototype.manual_rag.prepare download-model --output prototype/runtime/manual-rag/models/e5-small
prototype/runtime/manual-rag/venv/bin/python -m prototype.manual_rag.prepare build-index --model prototype/runtime/manual-rag/models/e5-small --output prototype/runtime/manual-rag/indexes/curated-v1
prototype/runtime/manual-rag/venv/bin/python -m prototype.server --manual-search hybrid --manual-index prototype/runtime/manual-rag/indexes/curated-v1 --port 8860
```

이미 파일이 있으면 다른 세대 경로를 지정한다. 모델·벡터 파일·가상환경은 `runtime/` 아래에 있어 Git 대상에서 제외된다. lock은 macOS Python 3.11 시험 환경의 버전 기록이며 다른 OS의 설치 성공을 보장하지 않는다. 원문 PDF도 별도 이용 조건을 확인한 뒤 배포한다.

LIVE는 기존 실행 파일과 동일하게 API 키·certifi 인증서 설정이 필요하다. 키를 명령줄·문서에 붙이지 않는다. 검색이 로컬이어도 현재 LIVE 생성은 외부 API다. 완전 오프라인 생성은 후속 작업이다.

## 4. 검색 계약

`ManualSearch(source=DEFAULT_SOURCE, mode='lexical'|'hybrid', index_dir=None)`를 앱 단위로 하나 만들고 `Engine(..., manual_search=search)`에 주입한다. 기본 `None`은 기존 동작이다. 검색 서비스의 Qdrant 작업은 전용 작업자 하나가 담당하며 요원 모델 호출은 기존 병렬 구조를 유지한다.

`retrieve(query, role='sar', incident=None, assignment='', budget_bytes=6000, context_parts=None)` 반환:

- `status`: `ok`, `partial`, `no_match`, `error` 등. 정상 검색도 내용의 충분성·정확도를 보장하지 않는다.
- `items`: 전체 요약·출처·판본·PDF 페이지·제한·초안 상태·본문 및 원본 PDF 해시와 `sar:` 근거 ID.
- `generation`, `method`, `warnings`, `omitted_ids`, `latency_ms`, `reason`.

벡터 후보와 BM25 후보 각각 최대 12개, RRF `1/(60+rank)`로 결합 후 최대 6개를 고려한다. 역할·임무는 관련 후보의 순위를 보조하며 무관한 지시를 일반적인 임무 문구로 매칭하지 않는다. 기본 dense 유사도 경계는 0.83이며 정확도 확률이 아니다. 복잡한 다중 질의 분해·추가 검색 루프는 미구현이다.

`context.py`는 현재 세션의 사용자 기록·사건 조건·이번 시뮬레이션 가정과 이미 요원에게 전달되는 Link-One 수신 근거를 검색에 함께 사용한다. 사실·가정·수신 자료의 라벨을 유지한다. 다른 세션·전체 대화·미승인 수신함은 검색하지 않는다. 필드를 통째로 선택하며 필드당 2,000바이트, 합계 6,000바이트, 최대 12개로 제한한다. 생략 시 `context_omitted`와 `partial`을 표시한다. 벡터 검색은 선택한 필드별 질의를 합치므로 일반 후속 지시도 사건 내용을 참고한다. 이는 사건 장부를 변경하지 않는다.

요원당 추가 자료는 완전한 JSON 항목의 UTF-8 크기 6,000바이트 안에서 공급한다. 이는 보수적인 고정 입력 크기 상한이며 실제 모델 토큰 한도를 계산한 결과가 아니다. 본문·조건을 중간에서 자르지 않고 들어가지 않는 항목은 `omitted_ids`로 남긴다. 전체 입력의 기존 180,000자 한도도 유지한다. 실제 모델별 tokenizer 예산은 로컬 모델 단계에서 보완한다.

## 5. 실패와 판본

- corpus 해시·페이지·공개 정책 오류: 앱 시작 시 검색 구성을 거절한다. `off`로 시작하면 기존 경로를 사용할 수 있다.
- 벡터 모델·인덱스 없음/불일치: 검증된 동일 corpus의 키워드 검색으로 대체하고 `degraded`를 표시한다. 정상 hybrid라고 표시하지 않는다.
- 특정 질의의 임베딩 실패: 해당 질의만 대체하며 다음 질의의 벡터 검색을 영구적으로 끄지 않는다.
- 새 자료·모델: 새 폴더로 인덱스를 만든 뒤 서버 시작 옵션을 변경한다. 실행 중의 세대는 바뀌지 않는다.
- 과거 보고: 당시 제공 본문·판본·해시는 SQLite 스냅샷에 유지된다. 현재 파일을 다시 검색해서 과거 입력을 재구성하지 않는다.
- 원본 PDF: 실행 당시 SHA-256을 링크에 포함한다. 등록부 판본 또는 실제 파일 해시가 달라지면 409와 제공 불가 사유를 반환한다. 과거 PDF를 별도 보관하지는 않으며 다른 판본으로 조용히 대체하지 않는다.

## 6. 저장·API

`objects.kind=manual_contexts`에 `run_id`, `stage`, `role`, `search`, `items`, 표시용 `evidence`를 저장한다. 모델 호출 전에 저장하므로 호출 실패도 당시 근거가 남는다. run의 `manual_context_ids`는 같은 SQLite 트랜잭션에서 추가한다. 세션 삭제 시 함께 삭제되고 진행 중 삭제 보호는 유지한다.

주기 snapshot의 `manual_contexts`에는 본문 `items`를 제외한다. 상세 API:

- `GET /api/sessions/{sid}/runs/{rid}/manual-contexts/{context_id}`: 세션·run·context의 소유 관계를 모두 검사한다. 불일치 404. 조회는 실행을 생성하지 않는다.
- `GET /api/manual-sources/{source_id}/pdf?sha256={original_sha256}`: 등록된 공개 PDF의 예상 판본과 실제 응답 바이트 해시를 검사한다. 해시 누락·판본 불일치 409, 미등록 출처 404. 임의 경로는 받지 않는다.
- `/api/config`: `manual_search.mode`, `ready_vector`와 실제 벡터 준비 상태를 반환한다.

새 보고의 선택 필드 `evidence_links`는 보고 문장·인용 ID·적용 이유·제한을 연결한다. ID·필드 형식 오류는 차단한다. 2026-09-30부터 문구만 불일치하는 연결은 유효 연결에서 제외하고 `unmatched_evidence_links`에 보존하며 `uncertainties`에 경고한다. 보고 문장을 수정하거나 유사 문구를 자동 매칭하지 않는다. 검증요원·최종 종합에 제외 이력을 전달하고 최종 보고에도 요원 연결 제외 경고를 보존한다. 정확히 연결된 문장도 근거가 의미상 뒷받침하는지는 별도 평가가 필요하다. 기존 `evidence_ids`는 보고 단위의 참조 목록으로 유지하며 문장별 검증 완료를 뜻하지 않는다.

## 7. 검증과 남은 한계

검증 결과는 [2026-09-29 실행 기록](../superpowers/plans/2026-09-29-sar-rag-progress.md)을 따른다. 테스트 명령:

```bash
prototype/runtime/manual-rag/venv/bin/python -m unittest discover -s prototype/tests -q
node prototype/tests/test_manual_ui.cjs
node --check prototype/static/manuals.js
node --check prototype/static/app.js
prototype/runtime/manual-rag/venv/bin/python -m prototype.manual_rag.evaluate --cases prototype/tests/fixtures/manual_rag/holdout.json --mode hybrid --index prototype/runtime/manual-rag/indexes/curated-v1 --offline --output prototype/runtime/manual-rag/holdout.json
```

벡터 라이브러리를 설치하지 않은 기본 Python 시험에서는 선택 의존성 시험을 skip한다. 브라우저는 Playwright가 있는 Node 환경에서 `CHROME_CHANNEL=chrome node prototype/tests/browser_manuals.cjs` 및 `browser_inbox.cjs`를 실행한다. 임시 DB를 쓰며 실제 운영 데이터와 분리한다.

현재 corpus는 14개 요약이다. 원문 561쪽 전체 검색·표 계산·전문 의료 처치·내부 매뉴얼·로컬 생성 모델은 미구현이다. 기존 키워드 출동 후보의 부정/종료 표현 해석 한계도 이번 검색 연결로 해결된 것이 아니다. 벡터 검색의 정확도 우위·현장 운용 적합성은 주장하지 않는다.


## 2026-09-30 · 기본 앱 실행 경로 활성화

사용자 요청으로 더블클릭 실행은 기본 앱 전용 curated-main-v1 인덱스와 전용 가상환경을 사용해 hybrid를 켠다. 직접 서버 CLI의 기본값 off는 그대로다. Qdrant 로컬 인덱스는 프로세스 간 공유하지 않으며 8861 시험 앱의 curated-v1은 보존한다. 현재 8860 HTTP 설정에서 hybrid·ready_vector=true를 확인했다. 새 인덱스 오프라인 holdout 12건 통과. 상세 준비·검증은 prototype/README.md와 PROGRESS.md의 2026-09-30 기록을 따른다.


## 2026-09-30 · 설정창에서 검색 전환

오른쪽 위 **설정 → 매뉴얼 벡터 검색 → 국제 SAR 매뉴얼 검색 사용**으로 켜기·끄기를 선택한다. 즉시 저장되며 서버의 모든 세션에서 다음 분석부터 적용하고 재시작 후에도 유지한다. 진행·대기 중 분석이 있으면 완료 후 변경한다. 꺼도 기본 매뉴얼·사건 기록·과거 근거는 유지한다. 벡터 환경이 준비되지 않은 서버는 켜기가 제한되므로 준비된 더블클릭 실행 파일을 사용한다. GET/POST `/api/settings/manual-search`는 enabled(boolean), 조회에는 available·mode·ready_vector를 제공한다. POST는 기존 세션 토큰 인증을 따른다. 전체205개 회귀시험과 브라우저 켜기·끄기·저장 확인을 완료했으며 최종은 켜짐이다.
