# 로컬 LM Studio 설정과 모델 전환

2026-09-30. 최신 사용자 요청으로 기존 OpenAI 고정 구성에 로컬 모델 선택을 추가했다. 기본 연결은 `http://127.0.0.1:1234/v1`, 모델은 `qwen/qwen3.6-35b-a3b`다. 기존 설정 버튼만 준비된 상태를 대체한다.

## 사용 흐름

1. LM Studio에서 로컬 서버를 실행하고 모델을 로드한다.
2. 해온 **설정 → AI 연결 → 로컬 LM Studio**를 선택한다.
3. 주소·모델 ID를 확인하고 **연결 확인**, **설정 적용**을 누른다.
4. LIVE 세션의 다음 지시부터 로컬 모델이 배정·전문요원·검증·종합을 맡는다. 새 세션도 실제 AI를 선택할 수 있다. 기존 DEMO 세션은 그대로 규칙 기반이다.
5. OpenAI로 돌아가려면 같은 설정에서 OpenAI를 선택해 적용한다. 서버 API 키가 없으면 이 선택은 비활성이다.

설정은 해당 서버가 사용하는 SQLite DB에 저장한다. 8860과 8861은 DB가 달라 각각 설정한다. 기능 배포 시 기존 OpenAI 선택을 보존했으며 자동으로 로컬로 바꾸지 않았다. 주소·모델은 기본 입력값으로 준비했다. 화면에는 LIVE·로컬 LLM 또는 LIVE·OpenAI로 연결을 표시하고 모델 이름은 설정에서 확인한다.

## 구현 계약

- `local_llm.py`: loopback 주소 정제, LM Studio 요청, 모델 목록 확인, JSON Schema, 호출 직렬화. http의 localhost/127.0.0.1/::1만 허용하고 자격정보·query·fragment·임의 경로를 거절한다. `/v1` 생략은 보충한다. proxy와 HTTP redirect를 사용하지 않는다. OpenAI 키를 로컬 요청에 전달하지 않는다.
- `models.py:model_input`: 기존 역할·외부 보고·링크온·매뉴얼·경사 지침과 검증 경량화를 공통 함수로 추출했다. 기존 OpenAI 지침 부분은 AST 비교로 동일함을 확인했다. OpenAI Responses 호출의 모델/medium은 유지한다.
- `engine.py`: 초기 설정 복원, 적용 시 전역 실행 lock과 SQLite queued/running 검사를 사용한다. 실행·대기 작업이 있으면 409로 거절한다. 링크온 수신 후 새로 접수될 분석은 그때의 선택을 따른다. 기존 세션·보고·초안을 변경하지 않는다.
- 실행 접수 시 run.model_config를 보존하고 실제 호출에는 provider/requested_model/reasoning_effort 및 응답 model·시간을 기록한다. 설정 조회만으로 AI를 호출하지 않는다. 로컬 실패를 OpenAI/DEMO 성공으로 바꾸지 않는다.
- 로컬 호출은 서버 Engine 하나당 semaphore 1개로 한 번에 1개 처리한다. 여러 임무의 배정·서버 작업 흐름은 유지하지만 모델 추론 호출은 차례로 진행한다. diagnostics.queue_ms로 대기와 추론 요청 시간을 구별한다. 생성 HTTP timeout은 180초, 모델 목록은 5초다.
- 로컬 생성은 `/v1/chat/completions`, JSON Schema를 사용한다. 현재 Qwen 조합에서 reasoning_effort=none, chat_template_kwargs.enable_thinking=false, /no_think 요청으로 최종 JSON 반환을 확인했다. 추론 원문을 읽거나 저장하지 않는다. 완료 이유가 stop이 아니거나 최종 content가 비었거나 dict JSON이 아니면 실패한다.
- 근거 ID는 각 호출에 실제 제공된 evidence ID의 enum으로 제한한다. 근거가 없으면 빈 배열만 허용한다. 선택적 evidence_links도 같은 ID 제한을 쓰고 기존 의미 검증을 통과해야 한다. 매뉴얼 검색 방식(off/lexical/hybrid)은 원래 서버 설정을 그대로 따른다.
- 로컬 final의 information_requests는 JSON 형식에서 최대 2개다. 로컬 LIVE 최종 보고는 모델이 고른 질문을 우선순위·동일문구 중복 제거 후 최대 2개 보존한다. 이전 배정/요원 질문을 다시 합치지 않으며 요원 원문은 tasks에 유지한다. 기존 Link-One 최종 질문 정책과 같은 경로를 재사용한다.
- 조회·설정 UI: `static/model-settings.js`, `app.js`, `index.html`. 서버가 같은 상태를 다른 탭에도 알 수 있도록 세션 snapshot에 llm 상태를 추가했다. 채팅 초안을 덮어쓰지 않는다. 저장 실패 시 이전 설정이 유지된다.

## HTTP

- `GET /api/settings/llm`: provider, base_url, model(로컬 입력값), openai_available, live_available.
- `POST /api/settings/llm/test`: base_url/model로 모델 목록에 ID가 있는지만 확인한다. 저장·실제 생성은 하지 않는다.
- `POST /api/settings/llm`: provider=openai/local과 로컬 주소·모델을 저장한다. 로컬은 적용 시에도 모델 목록을 확인한다. OpenAI 복귀는 저장된 로컬 입력값을 보존한다.
- 모든 POST는 기존 Host/Origin/X-Session-Token 검사를 따른다. 키를 반환하거나 저장하지 않는다. LM Studio 자체 인증 토큰·다른 PC의 LAN 주소는 이번 범위에 포함하지 않았다.

## 시험 기록

1. 실제 `/v1/models`에서 지정 모델 ID 확인. 최초 가상 짧은 JSON 생성은 stop이지만 content가 비고 reasoning_content만 있었다. 추론 비활성 요청을 추가하자 약 0.44초에 정상 최종 JSON을 받았다. 다른 모델/LM Studio 버전에도 같은 옵션이 통한다고 보장하지 않는다.
2. 신규 계약 시험 4개 미구현 오류 → 구현. 공통 지침 추출 첫 버전에서 다중행 문자열 들여쓰기 오류가 발생했으며 원본에서 다시 추출하고 기존 모델 계약 및 AST 비교로 수정 확인했다.
3. 실제 Qwen·격리 임시 DB·lexical 매뉴얼 가상 시험 1회: 배정9.28초, 정보13.05초, 검증13.26초, 종합15.11초, 총51.28초 completed. 매뉴얼 문맥3개 기록. 최종 질문이 많은 점을 확인했다.
4. 질문 Schema/근거 연결 보완 후 재시험은 검증 단계에서 미제공 근거 ID를 인용해 기존 서버 검증으로 failed(34.17초). 이를 성공으로 기록하지 않았다. 제공 ID enum으로 제한했다.
5. 제한 후 전체 재시험: 배정8.71초, 정보12.86초, 검증11.04초, 종합14.78초, 총48.42초 completed. 모델은 모두 지정 Qwen, 매뉴얼 문맥3개와 최종 SAR 인용3개 확인. 저장 질문이5개인 원인은 기존 엔진이 요원 질문을 합치는 처리였다. 신규 단위 시험에서 이를 재현하고 로컬 최종 선택 유지로 보완했다. 이 마지막 집계 보완 이후 실제 모델 전체 시험은 반복하지 않고 단위·전체 회귀로 검증했다.
6. 최종 Python189개 실행, 4 skip·나머지 통과. JavaScript 단위25개 통과. Node 최초 와일드카드가 browser 스크립트까지 포함해 playwright 모듈 부재 오류가 났으며 `test_*.cjs`로 단위 범위를 바로잡았다. 이를 새 브라우저 회귀 통과로 세지 않는다.
7. 격리 브라우저에서 연결 확인·로컬 저장·없는 모델 오류·이전 설정 보존·OpenAI 복귀·DEMO 유지·초안 유지 확인. 실제 운영 Qwen 생성은 하지 않았고 가상 세션만 사용했다. 신규 화면 전체 모바일 폭 회귀는 이번에 하지 않았다.
8. 8860/8861 모두 진행 AI/수신0을 확인하고 같은 DB·키·매뉴얼 off/hybrid·MCP off로 재시작했다. 세션13개/1개 ID 보존, 정적 JS 일치, 각 서버의 실제 LM Studio 연결 확인 API 성공. 기존 OpenAI 선택은 유지했다.

실측 시간은 위 가상 입력의 단일 실행 결과다. 긴 사건·여러 요원·다른 모델의 속도/품질을 보장하지 않는다. 로컬 LLM 전환은 생성 경로를 바꾸는 것이며 기상·Link-One 등 별도 네트워크 기능을 끄지 않는다. 검색·생성의 오프라인 운용 범위는 별도로 점검한다.

## 참고

[LM Studio Structured Output 공식 문서](https://lmstudio.ai/docs/developer/openai-compat/structured-output), [LM Studio API 변경 기록](https://lmstudio.ai/changelog/lmstudio). 사용자 PC에서 실제 호환성도 별도로 확인했다.

## 2026-09-30 검증 예산 구분

OpenAI 검증의 추론 예산 부족을 확인해 Responses 어댑터에서만6,000으로 복구했다. LocalModel은 기존 공통 입력 함수의 검증 상한2,400과 추론 비활성 요청을 유지한다. OpenAI 검증용 strict 근거 스키마 추가는 로컬 요청 형식을 변경하지 않는다. [측정 이력](33-linkone-llm-benchmark.md).
