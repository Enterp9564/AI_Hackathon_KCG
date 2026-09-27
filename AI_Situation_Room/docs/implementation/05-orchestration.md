# 05. 상황실장·병렬 요원·실행 상태

> 현재 구현 기준: 2026-09-27. [목록](README.md) · 구현: [engine.py](../../prototype/engine.py)

## 1. 역할과 책임

- commander(상황실장): 요청 범위·우선순위 판단, 임무 배정, 보고·정보요구 종합, 사용자 전달.
- intel(정보요원): 신고·명부·기상·자료의 출처와 불일치·누락 확인.
- sar(수색구조요원): 제공 지침과 위험·대응 선택 검토.
- resource(자원지원요원): 등록 세력 후보, 사용자 보고 운용 상태와 제약 검토.
- critic(검증요원): 수신 보고의 근거 누락·모순·가정 혼동 점검.

전문가 자격을 학습한 별도 모델들이 아니다. 같은 모델을 역할 지침·임무·근거로 구분한다. 모델은 실행 계획을 제안하고 실제 스레드·저장·도구 호출은 서버가 수행한다.

## 2. 큐와 동시 실행

- 세션 실행 ThreadPoolExecutor: max_workers=4.
- 전문요원 ThreadPoolExecutor: max_workers=6.
- 전체 모델 호출 BoundedSemaphore: 6슬롯. plan/report/final 모두 이 한도에 들어간다.
- `queues[sid]`는 run ID deque, `draining`은 현재 큐 소비 중인 세션 집합, `futures[rid]`는 완료 확인용 Future.

submit은 Engine 락 안에서 Store.enqueue를 호출하고, 새 queued run만 한 번 큐에 넣는다. 세션마다 drain 하나가 FIFO로 끝까지 처리한다. 실행 슬롯이 있어야 새 세션 drain이 시작한다. 무제한 세션에 대한 엄밀한 공정 스케줄러는 아니다.

독립 tasks를 모두 agents.submit한 다음 결과를 기다린다. `submit → result → 다음 submit`으로 순차 호출하면 요구를 충족하지 못한다. 현재 결과 수집은 제출 순서지만 각 task의 상태·보고는 완료 즉시 DB에 저장된다.

## 3. plan부터 장부까지

1. 최신 snapshot을 읽고 run을 running으로 바꾸며 started_at과 based_on_version을 설정한다.
2. 현재 run까지의 이력만 선택한다. 문맥 크기를 검사한다.
3. commander/plan을 호출하고 06의 결과 검증을 수행한다.
4. questions의 source·priority를 정규화한다.
5. 이전 세션 상태와 현재 prompt로 규칙 출동 후보를 만들고 모델 후보와 합친다. decision과 질문·제안 이벤트를 저장한다.
6. update가 있고 analysis이면 Store.apply_update를 수행한다. 최신 version·session·evidence를 실행 문맥에 다시 반영한다.
7. tasks가 비어 있으면 receipt로 종료한다. tasks가 있으면 전문요원 경로로 간다.

현재 규칙 후보는 갱신안 반영 전에 생성된다. plan 한 번의 결과가 모두 도착하기 전에는 전문요원을 시작하지 않는다.

## 4. 전문요원부터 최종 보고까지

각 요원은 assigned Task를 먼저 저장한다. 슬롯을 얻은 뒤 running과 시작시각을 저장하고 보고 호출을 한다. 성공은 report·completed·종료시각·보고 수신 이벤트를 남긴다. 정보요구가 있으면 상황실장 앞으로 별도 이벤트를 남긴다.

모든 선택 요원이 성공하면 critic를 한 번 호출한다. critic은 앞선 보고의 사본을 받는다. 그 후 commander/final이 전문요원+검증 보고를 종합한다. 자동 보완 재배정·재시도 루프는 없다.

최종 저장 전 서버가 추가하는 값:

- 정보요구: plan → 각 보고(critic 포함) → final 순서로 합치고 질문 문자열이 같은 것만 제거.
- 출동 지시안: 기존 decision 후보를 먼저 유지하고 final 후보를 ID 기준으로 병합.
- timeline: 현재 run까지의 simulation 제외 사용자 원문, source_id, received_at.
- report_ids: 실제 수신한 전문요원·critic Task ID.
- basis_version: run.based_on_version, assumptions: 요청 가정.

최종 완료 시 세션 version이 달라졌다면 stale로 보존한다. 최신 장부로 자동 덮어쓰거나 자동 재검토하지 않는다.

## 5. 실패 처리

- 요원 하나가 실패해도 이미 제출한 나머지 작업은 끝까지 기다린다. 성공한 개별 보고는 남긴다.
- 하나라도 실패하면 critic/final을 계속 성공 처리하지 않고 run.failed와 error를 저장한다.
- ModelError·ValueError의 안내 문구는 사용자에게 전달한다. 그 외 오류는 내부 예외 세부 대신 일반 안내를 저장한다.
- 호출 실패도 calls에 남는다. UI 연결 끊김과 모델 실패는 다른 상태다.
- 요청 HTTP 202 이후 실패는 snapshot의 run.error로 전달된다. 이미 반환한 HTTP 상태를 바꾸지 않는다.
- Engine.wait의 30초는 시험 보조 대기 한도다. LIVE API의 90초 timeout이나 전체 run 제한시간이 아니다.

## 6. 최신 목표와 현재 차이

목표는 `접수 → 짧은 범위 판단 → 전문요원 먼저 배정 → 보고·정보요구 → 검증 → 핵심 제안`이다. 현재 plan은 장부 갱신안 추출과 배정을 함께 수행하며 프롬프트에 단순 정정 직접 반영 규칙도 남아 있다. 빠르게 보이는 UI만으로 실행 책임 분리가 완료되지 않는다.

개선 방향은 첫 호출의 산출물을 짧은 scope·tasks로 제한하고, 신고 추출은 지정 요원, 수량·버전 검사는 서버에 두는 것이다. 규칙 출동 후보는 전문 검토와 최신 장부를 근거로 종합하도록 이동한다. 구체적인 새 JSON 계약은 구현 작업에서 정하고 02·06도 함께 갱신한다. 현재 계약이 이미 바뀐 것으로 구현하지 않는다.

## 7. 수용 기준

- 선택된 역할만 1회 실행, 같은 역할 중복 배정 거절, critic은 모든 독립 보고 뒤에 실행.
- 최소 두 전문요원의 started_at~ended_at 구간이 실제 중첩.
- 동일 세션 후속 요청은 앞선 최종 결과를 읽고 미래 큐 원문은 읽지 않음.
- 다른 세션으로 UI를 전환해도 작업의 session_id가 바뀌지 않음.
- 실패·중단·stale 표시와 성공을 구별, LIVE 실패에 DEMO fallback 없음.
- 배정 경량화 후 접수→배정, 첫 전문 보고, 최종 보고 시간을 따로 측정. 현재 미측정 성능 목표를 통과로 쓰지 않음.

## 2026-09-27 추가: 승인된 외부 보고

[수신함](16-external-inbox.md)의 인용 승인만 기존 submit 큐로 들어온다. 인용 run은 장부 update를 제거하며 요원 배정이 없으면 정보요원 검토를 추가한다. 이후 일반 장부 추출에는 외부 인용과 이를 사용한 후속 요약을 제외한다. 요원은 갱신 후 최신 context 근거를 사용하며, 최종 보고는 사용 가능한 외부 출처 ID 목록을 메시지에 보존한다.
