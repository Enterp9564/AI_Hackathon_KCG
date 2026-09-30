# HAEON(해온) — 실행형 프로토타입

> **2026-09-30 실행 기본값 변경:** 루트 `상황실 실행.command` 더블클릭은 준비된 `runtime/manual-rag/venv/bin/python`과 기본 앱 전용 `runtime/manual-rag/indexes/curated-main-v1`을 사용해 8860을 **hybrid 벡터 검색 활성**으로 시작한다. 준비되지 않은 환경은 안내 후 중단하며, 이미 실행 중인 서버가 검색 비활성이면 종료 후 재실행하도록 안내한다. 아래 `python3 -m prototype.server` 직접 실행의 CLI 기본값은 여전히 `off`다. 8861 시험 서버의 `curated-v1`과 Qdrant 저장 폴더를 공유하지 않는다.

새 PC에서는 국제 SAR 검색 준비 절차에 따라 전용 가상환경·모델을 준비한 뒤 기본 앱용 인덱스를 만든다:

```sh
prototype/runtime/manual-rag/venv/bin/python -m prototype.manual_rag.prepare build-index --model prototype/runtime/manual-rag/models/e5-small --output prototype/runtime/manual-rag/indexes/curated-main-v1
```

이미 준비된 인덱스는 덮어쓰지 않는다. 자료·모델을 바꾸면 새 인덱스 경로를 만들고 실행 파일의 경로도 맞춘다.


> 임시 프로젝트명: **HAEON(해온)** · 해양경찰 멀티에이전트 의사결정 지원 시스템. [명칭·소개 기준](../docs/PROJECT_NAMING.md) (2026-09-27). ‘AI 오케스트라’는 협업 방식의 설명이며 이름에 포함하지 않는다.

> 구현을 이어갈 AI: [기능별 상세 구현 문서](../docs/implementation/README.md) · [향후 프로젝트 API 연동](../docs/improvements/01-project-api-integration.md). 상세 명세는 2026-09-27 소스를 대조했으며 기존 시험 결과와 구별한다.

> 2026-09-26. [현재 요구와 구현 차이](../13_현재상태_요구사항_인수인계.md) · [진행·검증 기록](PROGRESS.md)

Python 3.11+ 표준 HTTP 서버·SQLite·HTML/CSS/JavaScript로 실행한다. 별도 웹 프레임워크는 필요 없다. macOS 실행 파일은 TLS 인증서를 위해 `certifi`도 사용한다. 발표 자료는 별도 `presentation/`에 있다.

## 선택 기능: 국제 SAR 로컬 검색 — 2026-09-29

공개 국제 SAR 한국어 요약 14개를 요원·검증·최종 보고의 근거로 연결했다. 기본값은 `off`이며 기존 더블클릭 실행은 그대로다. 키워드 시험은 `python3 -m prototype.server --manual-search lexical`, 준비된 벡터 시험은 `prototype/runtime/manual-rag/venv/bin/python -m prototype.server --manual-search hybrid --manual-index prototype/runtime/manual-rag/indexes/curated-v1`로 실행한다. 실행 중인 서버는 종료한 뒤 재시작한다.

[상세 설치·실행·저장 계약](../docs/implementation/24-local-manual-rag.md) · [검증 기록과 범위](../docs/superpowers/plans/2026-09-29-sar-rag-progress.md). 보고의 국제 SAR 버튼에서 당시 전달한 근거·페이지·적용 제한을 확인한다. 검색만 로컬이며 LIVE 생성은 기존 외부 API다. 원문 전체 검색과 로컬 생성 LLM은 후속 단계다.

## 더블클릭 실행

1. `prototype/.secrets/openai_api_key.txt`에 API 키 한 줄을 직접 저장한다. 확장자는 `.txt`가 맞다. 숨김 폴더는 Finder에서 **Command+Shift+.**으로 표시한다.
2. 프로젝트 루트 **상황실 실행.command**를 더블클릭한다. 키를 읽어 서버 환경에 전달하고 브라우저를 연다. `certifi`가 없으면 안내에 따라 `python3 -m pip install certifi`를 실행한다.
3. 사용 중 터미널을 열어두고 종료는 **Control+C**로 한다.

서버가 이미 켜져 있으면 실행 파일은 브라우저만 연다. 코드·모델·API·키 변경 적용은 **서버 종료 → 더블클릭 재실행 → 브라우저 새로고침** 순서다.

- 담당자: [http://127.0.0.1:8860/](http://127.0.0.1:8860/)
- 고정 상황판: [http://127.0.0.1:8860/monitor](http://127.0.0.1:8860/monitor)
- 저장: `prototype/runtime/room.sqlite`. 서버 종료 후 runtime 폴더를 복사해 백업한다.
- 키·runtime·환경설정 원본은 발표 배포물에 넣지 않는다. 키 값은 소스·문서·화면·로그에 쓰지 않는다.

직접 실행은 프로젝트 루트에서 다음 명령을 사용한다. 서버 자체는 키 파일·`.env`를 자동으로 읽지 않으므로 `OPENAI_API_KEY`·인증서 환경은 별도 설정이 필요하다.

```sh
python3 -m prototype.server --port 8860
```

별도 DB는 `--db /원하는/경로/room.sqlite`로 지정한다. localhost 전용이며 사용자 인증·외부 배포 기능은 없다.

## 기본 사용

1. **새 세션**에 이름을 입력한다. 키가 있으면 실제 AI가 기본 선택된다. 키가 없으면 LIVE를 선택할 수 없고 명시적 데모만 사용할 수 있다. 기존 DEMO는 자동 전환되지 않는다.
2. 신고·정정·질문을 입력하고 **Enter**로 보낸다. **Shift+Enter**는 줄바꿈이며 한글 조합 중 Enter는 전송하지 않는다.
3. 즉시 접수 효과와 상단 ‘지시 수행 중’, 임무·보고·실행 시간축·최종 제안을 확인한다. 질문에는 이유와 요청 요원이 표시된다. 질문·출동안은 각각 앞 2건을 보여주고 나머지는 펼친다.
4. **시뮬레이션 조언**에서는 변경 가정을 입력한다. 조건 비교는 현재 장부를 바꾸지 않는다.
5. **상황판에 고정 → 대형 화면 ↗**을 연다. 담당자가 다른 세션으로 바꿔도 고정 화면은 유지된다. **상황실로 돌아가기 ↩**으로 복귀하고 브라우저 전체화면은 버튼 또는 Esc로 해제한다.
6. 목록 **×**는 확인 후 삭제한다. 대기·진행 중 지시가 있으면 거절한다. 고정된 세션 삭제 시 고정도 해제하며 외부 백업 파일은 남는다.

화면은 약 1초마다 상태를 조회한다. 이 조회만으로 AI·기상을 호출하지 않는다. 같은 세션 지시는 순차, 독립 세션·요원은 병렬로 처리한다. 지연 10초 초과·연결 끊김 30초 초과를 구별한다. 상세 창은 열람 시점 자료이므로 최신 값은 닫고 다시 연다.

## 자료·기억

CSV는 UTF-8의 `id,rescued` 열을 쓴다. ID는 중복 없이, rescued는 true/false 또는 1/0이다. TXT/MD도 지원하며 파일당 100KB까지다.

```csv
id,rescued
training-01,true
training-02,false
```

첨부만으로 현재 총원을 확정하지 않는다. LIVE 신고·명시적 정정은 모델의 갱신안을 서버가 검사해 저장한다. 인물 ID·이전 상태·원문을 보존하고 인원 분포·환자 그룹을 관리한다. 자료·보고·가정은 세션별로 격리한다.

현재는 단어 기반 검색과 공통 매뉴얼·사용자 제공 동해 세력 근거를 사용한다. Chroma·벡터 RAG·긴 기억 자동 요약은 없다. Link-One·RESAID AI용 승인형 MCP 수신함은 제공한다. 입력 한도를 넘으면 기존 기록을 보존하고 오류를 알린다. 작성 중 초안은 현재 브라우저 메모리에 유지하며 새로고침 후 복원은 보장하지 않는다.

기상 **조회 ↻**는 입력한 위도·경도로 Open-Meteo Forecast를 수동 호출한다. 위치 변경 시 오래된 기상을 무효화한다. 실응답 성공은 추가 검증 대상이며 파고·자동 스케줄·현장 실측은 미연동이다.

## 실제 AI와 현재 한계

요청 모델은 `gpt-6-luna`, 전 역할 `reasoning.effort=medium`이다. 운영 화면에서 모델명·추론 수준을 숨기고 요청·응답 ID·사용량·시간은 기록한다. 키 존재와 API 성공은 별개다.

LIVE는 세션의 요청·장부·근거를 API로 전달한다. DEMO는 규칙 기반이며 AI를 호출하지 않는다. LIVE 실패를 데모 성공으로 바꾸지 않는다.

전문요원 선택·병렬·검증·종합은 구현했다. 첫 plan은 아직 장부 해석·갱신안까지 포함하므로 빠른 배정의 실행 분리는 남아 있다. 출동안은 키워드 규칙과 모델 결과를 결합하며 기출동·위험 해소에도 반복 제안할 수 있다. 실제 거리·ETA·가동 조회·외부 명령 전송은 없다.

조건 비교는 가정 기반 검토이며 물리 시뮬레이션·구조 성공률 예측·자동 과거 시뮬레이션 재사용은 미구현이다.

## 검증

```sh
python3 -m unittest prototype.tests.test_engine prototype.tests.test_incident prototype.tests.test_models prototype.tests.test_store -q
node --check prototype/static/app.js
python3 prototype/scenarios/check_saved_run.py prototype/runtime/cheonghae-live-test-v3.json
```

2026-09-26 핵심 단위 39개·JS 문법·기존 v3 저장 검사 PASS를 확인했다. runtime 시험 파일은 로컬 보존 자료여서 배포본에 없을 수 있다. 전체 테스트 명령은 `python3 -m unittest discover -s prototype/tests -q`이며 추가 HTTP 3개에 로컬 포트 바인딩 권한이 필요하다. 전체 명령은 이번에 실행하지 않았다.

[청해호 15건 원문](scenarios/cheonghae-fire.md) · [최초 LIVE 실패](scenarios/cheonghae-test-results.md) · [개선 결과](scenarios/cheonghae-improvement-results.md)

과거 LIVE는 당시 설정의 결과다. 최신 medium·UI·매뉴얼 변경 후 새 LIVE 전체 시험과 브라우저 동선·실제 장비 거리·2시간 내구성 검증은 남아 있다.

## Link-One · RESAID AI 연결 준비

[MCP·핫스팟 테스트 안내](../docs/implementation/18-hotspot-testing.md)에서 인증 파일 생성 → 서버 시작 → 사건 ID 연결 → 테스트 보고 제출 순서를 따른다.

```sh
python3 -m prototype.prepare_mcp
python3 -m prototype.server --mcp-port 8862
```

기본은 같은 PC 시험이다. 핫스팟에서는 --mcp-host와 --mcp-allowed-host를 지정한다. 담당자 화면/API는 loopback으로 유지한다. 수신만으로 AI/상황판을 변경하지 않으며, 프로젝트 알림의 **인용하여 전송**에서만 기존 지시를 실행한다. 초안은 유지되고 미확인 보고를 사실로 자동 반영하지 않는다.

도구 계약은 [MCP 수신 서버](../docs/implementation/17-mcp-transport.md), 상태·이력은 [외부 수신함](../docs/implementation/16-external-inbox.md)을 읽는다. 실제 팀 앱·핫스팟 장비·이번 변경의 LIVE 호출 검증은 아직 하지 않았다.

## 공개 국제 SAR 자료 — 2026-09-28

[로컬 매뉴얼 자료](manuals/library/README.md)에 공개 국제 SAR 기반 초안을 준비했다. AMSA 2026 SAR 매뉴얼과 IMO 회람 5개의 원본 PDF, 페이지별 추출 텍스트, 한국어 분야별 초안 8개, 선별 구절 14개를 포함한다. 국내 안내·사례는 보조 자료다.

현재 앱은 기존 기본 매뉴얼만 자동으로 읽는다. 새 분야별 MD는 기존 첨부 흐름에 넣을 수 있는 형식으로 준비했으며, 자동 구절 검색·Vector DB·로컬 LLM·일반 웹 검색 연결은 아직 없다. 내부 자료 연결 전에는 로컬 모델 경로와 외부 전송 차단을 구현해야 한다. 자세한 범위와 후속 설계는 [매뉴얼 로컬화](../docs/improvements/03-local-manuals.md)를 따른다.


## 링크온 개발 DB 접속 준비

현행 절차는 [DB 연결·동기화 운영 문서](../docs/operations/linkone-db-connection.md)를 따른다. 새 PC 준비부터 키 등록, 서버 지문 검증, DB 점검, 앱 수신, 장애 대응과 종료 절차까지 정리했다. 아래 준비 기록은 과거 검증 이력이다.

[로컬 설정·공개키 전달·점검 명령](../docs/handoff/linkone-access/README.md)을 따른다. `linkone_access.py`는 독립 수동 접속 점검 도구이며 해온 서버 실행이나 자동 데이터 수신을 변경하지 않는다. 공개키 등록 후 터널과 DB 점검을 실행한다. 비밀·가상환경은 `.secrets/linkone/`에만 보관한다.

### 링크온 수동 동기화 (2026-09-28)

사이드바 **링크온 동기화** → 사건 선택 → 전용 세션 수신 → 자동 분석. 실제 DB 읽기 연동이며 기존 MCP 수신함과 별도입니다. 표별 대기 없이 수신하며, 연속 수신 요청 사이에는 5초 간격을 둡니다. 동일 자료는 분석을 반복하지 않습니다. **승선원 · 변경 내역**에서 검색·전후 비교·과거 수신본을 확인합니다. LIVE/DEMO를 구별하고 자동 원격 폴링은 하지 않습니다. 접속 준비·데이터 범위·한도·API는 [구현 문서](../docs/implementation/linkone-manual-sync.md)를 참조하세요.

## 로컬 LLM 선택 — 2026-09-30

LM Studio 서버를 실행한 뒤 해온 **설정 → 로컬 LM Studio → 연결 확인 → 설정 적용**을 사용한다. 기본 주소는 `http://127.0.0.1:1234/v1`, 모델은 `qwen/qwen3.6-35b-a3b`. LIVE 세션의 다음 지시부터 적용하며 DEMO는 유지한다. 설정은 서버 DB별로 저장한다. [설정·호환성·검증](../docs/implementation/32-local-llm-settings.md).


## 2026-09-30 · 설정창에서 검색 전환

오른쪽 위 **설정 → 매뉴얼 벡터 검색 → 국제 SAR 매뉴얼 검색 사용**으로 켜기·끄기를 선택한다. 즉시 저장되며 서버의 모든 세션에서 다음 분석부터 적용하고 재시작 후에도 유지한다. 진행·대기 중 분석이 있으면 완료 후 변경한다. 꺼도 기본 매뉴얼·사건 기록·과거 근거는 유지한다. 벡터 환경이 준비되지 않은 서버는 켜기가 제한되므로 준비된 더블클릭 실행 파일을 사용한다. GET/POST `/api/settings/manual-search`는 enabled(boolean), 조회에는 available·mode·ready_vector를 제공한다. POST는 기존 세션 토큰 인증을 따른다. 전체205개 회귀시험과 브라우저 켜기·끄기·저장 확인을 완료했으며 최종은 켜짐이다.
