# 10. 담당자 화면과 상호작용

> 임시 프로젝트명: **HAEON(해온)** · 해양경찰 멀티에이전트 의사결정 지원 시스템. [명칭·소개 기준](../PROJECT_NAMING.md) (2026-09-27). ‘AI 오케스트라’는 협업 방식의 설명이며 이름에 포함하지 않는다.

> 현재 구현 기준: 2026-09-27. [목록](README.md) · 구현: [index.html](../../prototype/static/index.html), [app.js](../../prototype/static/app.js), [style.css](../../prototype/static/style.css)

## 1. 화면 구조

담당자 경로는 `/`다. 왼쪽 고정 사이드바에 새 세션·세션 목록·삭제 ×·구현 범위 안내를 둔다. 본문 상단은 세션 제목·ID·상황 버전, LIVE/DEMO, 고정·대형화면 버튼, 연결 상태·시계, 수행 상태 배너 순서다.

세션이 없으면 새 세션 생성 안내를 표시한다. 선택 세션이 있으면 아래를 배치한다.

- 대화: 사용자 원문·상황실장 답변·상세 버튼, 분석/시뮬레이션 선택, 가정 입력, prompt, 첨부·전송.
- 실행: 상황실장 배정 → 선택 전문요원 카드 → 검증 → 최종 보고, 실행 선택 목록과 실제 시간축.
- 현재 상황: 총원·구조·잔류, 위치·좌표·출처·명부 요약, 기상, 공통 자료·세션 첨부.
- 하단: 최근 이벤트 최대 3건.

색상은 어두운 남색 배경, 청록색 진행·제안, 주황색 질문·확인, 붉은 오류를 기본으로 한다. 정확한 디자인 토큰은 CSS가 소유한다. 기능을 새 프레임워크로 바꾸지 않는다.

## 2. 필수 DOM 연결점

- 선택: newSession, startSession, sessionList, sessionCount, sessionTitle, sessionMeta.
- 입력: prompt, assumptions, analysisMode, simulationMode, assumptionsLabel, send, attach, fileInput.
- 출력: messages, newMessages, flow, runSelect, executionStatus, timeline, concurrency.
- 상황: priority, facts, editFacts, weather, weatherButton, evidence, attachmentCount, events.
- 공통: connection, clock, modeBadge, pinButton, modal, modalTitle, modalBody, closeModal, toast.
- 상황판 전용: backToRoom, fullscreen. `/monitor`에서는 body.monitor를 사용한다.

## 3. 초기화와 폴링

초기에 GET config → GET manuals → refresh 순서로 실행한다. refresh는 sessions → monitor의 고정 ID → 선택 세션 snapshot을 읽는다. 약 1초 주기이며 polling 플래그로 중첩 호출을 막는다.

sid, snapshot, runId, generation, lastSync를 별도로 관리한다. 세션을 전환할 때 generation을 증가시키고 이전 DOM·snapshot을 초기화한다. snapshot 응답의 target ID와 generation이 현재와 다르면 늦은 응답을 버린다.

선택 ID가 없으면 localStorage의 마지막 ID가 목록에 있는지 확인하고, 없으면 최신 생성 세션을 선택한다. 입력 요소를 매번 재생성하지 않는다. session/message/run/content signature가 바뀐 영역만 다시 그린다. 현재 세션 snapshot에는 전체 이력이 포함되므로 긴 세션의 성능은 별도 개선 대상이다.

## 4. 전송과 입력 보존

- Enter는 전송, Shift+Enter는 줄바꿈. `event.isComposing`이면 전송하지 않아 한글 조합을 보호한다.
- sid가 없거나 이미 sending이면 중복 전송을 막는다. 빈 prompt, simulation의 빈 가정은 안내한다.
- 전송 직전에 대상 sid와 payload를 고정한다. UUID request_id를 생성하고 동일 payload의 실패 재시도에는 같은 ID를 쓴다.
- 서버 응답 전 즉시 접수·라우팅 표시를 하고 send를 비활성화한다. 완료율을 만들지 않는다.
- HTTP 202 성공 후 같은 세션의 같은 초안만 지운다. 전송 도중 바꾼 다른 초안을 지우지 않는다.
- 실패하면 prompt와 재시도 ID를 남기고 오류 안내를 한다. finally에서 send를 다시 활성화한다.
- 세션 전환 시 prompt/assumptions/kind를 drafts Map에 저장한다. 새로고침 복구는 보장하지 않는다.

현재 즉시 접수 카드에 LIVE 고정 문구가 있어 DEMO 표시 일관성은 개선 대상이다. 실제 mode 판정은 Session.mode와 배지를 기준으로 한다.

## 5. 진행·보고

실행 선택은 사용자가 고른 run 우선, 없으면 최신 running, 없으면 마지막 run이다. queued는 대기, decision 전은 요청 판단, task assigned/running은 배정·검토, 완료 보고는 종합·완료 상태를 보여준다. 실패·중단·stale은 각각 따로 안내한다.

선택되지 않은 역할은 미배정으로 표현한다. 배정 이유·임무·개별 결과·정보요구 수와 실제 시각을 표시한다. 직접 반영(tasks=[]) 경로는 ‘요원 추가 호출 없음’으로 표시한다. 내부 추론·퍼센트 진행률·가상 완료 로그를 생성하지 않는다.

최종·개별 보고 상세에는 요약, 출동안, 질문/이유/출처, findings, 원문 경과(있는 경우), 권고, 가정·불확실성, evidence를 표시한다. 모델명·추론 수준은 화면에 노출하지 않는다. 상세 dialog는 연 시점 자료로 유지되어 최신 내용은 닫고 다시 열어야 한다.

## 6. 현재 상황과 신선도

잔류 값은 facts.remaining이 있으면 ‘선내 잔류’, 없고 total/rescued가 있으면 차이를 ‘미구조(집계)’로 표시한다. 모르는 숫자는 0 대신 —를 쓴다.

우선 안내는 첨부 총원 불일치 → 기준 버전 불일치 → 실패/중단 → simulation 안내 순서로 선택한다. 명부 상세는 인물·분포·환자·자산·위험과 source_id에 연결된 before/patch 이력을 보여준다.

lastSync 이후 10초 초과~30초는 갱신 지연, 30초 초과는 연결 끊김이다. 이는 서버 수신 신선도이며 현장 사실이나 기상 관측의 최신성을 뜻하지 않는다. 연결이 끊겨도 마지막 값을 유지하고 오래된 값임을 표시한다.

## 7. 사용성·오류·반응형

채팅이 하단 90px 이내에 있으면 새 메시지 때 아래로 이동한다. 이전 메시지를 읽는 중이면 스크롤을 유지하고 ‘새 보고 보기’를 표시한다. 동적 문자열은 esc 또는 textContent로 렌더한다. 상태 배너·메시지에는 aria-live, 입력·버튼에는 식별 가능한 label을 둔다.

브라우저 fetch timeout은 일반 10초, weather 22초다. 토스트는 약 5초 표시한다. 실제 모델 완료는 message 응답 timeout과 분리한다.

CSS는 대형 3열, 1390px 이하 상황 영역 아래 배치, 1000px 이하 주요 1열, 620px 이하 모바일 사이드바 재배치가 있다. prefers-reduced-motion에서 애니메이션·전환을 줄인다. 최신 브라우저 시각 검증·실제 원거리 가독성은 미실시다.

## 8. 수용 기준

한글 입력·줄바꿈·전송 실패·세션 전환 초안·중복 요청·늦은 snapshot 무시·스크롤 유지·상세 원문 연결을 확인한다. UI에 남아 있는 ‘세션 삭제 미구현’ 안내, DEMO 접수의 LIVE 문구, 타 탭 삭제 후 선택 복구는 후속 수정 대상이다. 문서 작업으로 UI를 수정했다고 기록하지 않는다.
