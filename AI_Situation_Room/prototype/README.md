# AI 종합상황실 — 실행형 프로토타입

> 구현을 이어갈 AI: [기능별 상세 구현 문서](../docs/implementation/README.md) · [향후 프로젝트 API 연동](../docs/improvements/01-project-api-integration.md). 상세 명세는 2026-09-27 소스를 대조했으며 기존 시험 결과와 구별한다.

> 2026-09-26. [현재 요구와 구현 차이](../13_현재상태_요구사항_인수인계.md) · [진행·검증 기록](PROGRESS.md)

Python 3.11+ 표준 HTTP 서버·SQLite·HTML/CSS/JavaScript로 실행한다. 별도 웹 프레임워크는 필요 없다. macOS 실행 파일은 TLS 인증서를 위해 `certifi`도 사용한다. 발표 자료는 별도 `presentation/`에 있다.

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

현재는 단어 기반 검색과 공통 매뉴얼·사용자 제공 동해 세력 근거를 사용한다. Chroma·벡터 RAG·MCP·긴 기억 자동 요약은 없다. 입력 한도를 넘으면 기존 기록을 보존하고 오류를 알린다. 작성 중 초안은 현재 브라우저 메모리에 유지하며 새로고침 후 복원은 보장하지 않는다.

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
