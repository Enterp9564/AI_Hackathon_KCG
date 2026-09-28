# 21. 입력부터 저장·보고까지의 계약 예제

> 2026-09-28. 고정 ID·시각은 설명용이다. 실제 UUID·시각·모델 문장은 달라질 수 있다. 예제는 LIVE 실행 기록이 아니다.

## 사례 A — 분석 경로

1. POST /api/sessions에 `{ "title":"재구현 검증 A", "mode":"demo" }` → 201, S0·facts={}.
2. POST facts에 `{ "version":0, "facts":{"total":8,"rescued":3,"remaining":5,"location":"묵호 동방 5해리"} }` → 200, S1. 이것은 명시적 사용자 사실 입력이다.
3. POST message에 `{ "prompt":"인원만 검토해줘", "request_id":"example-a-1" }` → 202 Run. 원문 1개, queued run 1개, received event 1개가 같은 트랜잭션으로 생긴다.
4. DEMO plan은 intel 한 명 배정. run.running → task intel assigned/running/completed → critic → commander final → run.completed. DEMO는 장부 자동 추출을 하지 않아 S1 유지.
5. 일반 전문 검토의 Call 순서는 commander.plan → intel.report → critic.report → commander.final, 총 4회다. 같은 request_id 재전송은 기존 run이므로 추가 Call 0회.
6. snapshot은 정확히 `session/messages/runs/tasks/events/attachments/calls/server_time` 키를 제공한다. task 2개(intel·critic), 사용자/상황실장 메시지 2개, final.report_ids는 두 Task ID다. report의 basis_version과 run/message의 based_on_version은 1이다.

API 최소 왕복 예제는 13의 Python 예제를 따른다. 원격 모델 접근 없이 이 사례의 저장·접수·직렬화·표시를 먼저 만든다.

## 사례 B — 이름 정정과 수량 검증

초기 현재 상태(일부):

```json
{
  "facts":{"total":8,"rescued":6,"remaining":2},
  "incident":{
    "distribution":{"청해호":2,"동진호":3,"연안구조정":3},
    "roster":{"engineer-01":{"name":"이기란","role":"기관장","location":"청해호","condition":"의식 명료, 부상 보고 없음","lifejacket":"착용"}}
  }
}
```

명시 이름 정정의 patch:

```json
{"roster":{"engineer-01":{"name":"이기관"}}}
```

기대: 동일 engineer-01의 name만 변경, 나머지 4필드·facts·distribution 유지. 저장 version은 실제 변경 시 1 증가, incident_updated에는 before/after/patch/source_id/run_id가 남는다. 과거 Message의 ‘이기란’은 유지한다.

이후 전원 구조 patch:

```json
{"facts":{"rescued":8,"remaining":0},"distribution":{"동진호":3,"연안구조정":3,"301함":2},"roster":{"engineer-01":{"location":"301함"}}}
```

기대: total 8 유지, 청해호 이전 분포 제거, rescued 8. 기관장 이름·건강·구명조끼 유지. `distribution:{"301함":9}`는 합계 불일치로 전체 거절한다. 함께 온 facts·명부 필드도 일부 저장하면 안 된다.

최종 재이송 patch는 distribution을 `{"301함":5,"묵호항":3}`로 교체한다. rescued 8을 더 증가시키지 않는다. 같은 patch를 같은 run으로 반복하면 추가 version/event가 없어야 한다. 다른 patch로 같은 run을 재사용하면 Conflict다.

## 사례 C — 세션과 동시성

A에는 total 8, B에는 total 2. A의 요청 1·2를 빠르게 접수하고 B의 요청도 접수한다. A1 → A2 순서는 보존한다. A1이 A2 원문을 미리 읽으면 실패다. B는 별도 세션 슬롯에서 실행될 수 있다. A2는 A1 완료 결과를 참고한다.

독립 intel/sar가 있는 요청은 두 작업을 먼저 제출하고 나중에 기다린다. 실행 구간 `[started_at,ended_at]`의 교집합이 0보다 커야 병렬 실행 증거다. 한 요원이 실패하면 성공한 다른 보고는 남기되 critic/final 성공을 만들지 않는다. 처리 중 수동 facts 수정으로 S2가 되면 S1 기준 완료 보고는 stale로 남는다.

## 사례 D — 가정 비교

facts.total=8 상태에서 kind=simulation, assumptions='승선원이 10명이라고 가정'으로 요청한다. 성공 여부와 무관하게 실제 facts/incident는 그대로다. 원문·Run의 kind/assumptions는 유지한다. 일반 병렬 final에는 assumptions가 들어간다. simulation 원문을 사실 근거나 실제 경과 timeline에 넣지 않는다. 현재 무임무 receipt 경로의 가정 누락은 09의 알려진 차이이며 새 구현의 개선 인수에서 확인한다.

## 사례 E — 승인형 외부 보고

1. 로컬 sid A에 project=link-one, incident_id=training-a 연결.
2. MCP submit_field_report 입력:

```json
{"report_id":"example-external-1","incident_id":"training-a","incident_title":"훈련 사고","reported_at":"2026-09-28T09:00:00+09:00","content":"총원 9명이라는 현장 보고. 아직 확인 중."}
```

3. receipt.status=pending. 원문 저장·알림만 발생한다. A의 facts.total=8, version, messages/runs/tasks/calls 개수는 그대로다.
4. 로컬 POST /api/sessions/A/message에 `{ "inbox_report_id":"서버 receipt ID", "kind":"analysis" }` → 202, 원문 인용 사용자 지시 1개. 서버 요청 ID는 inbox:receiptID. 수신함은 sent이며 이는 AI 완료를 뜻하지 않는다.
5. 모델 update.total=9를 반환해도 인용 run은 장부를 바꾸지 않는다. 최소 intel 검토를 배정한다. final의 외부 출처를 다음 일반 요청의 사실 추출 문맥에 무표시로 넣지 않는다.
6. 같은 원문/보고 ID 재수신·같은 receipt 재승인은 기존 접수/run을 반환한다. 같은 ID에서 content만 변경하면 충돌, B에서 승인하면 충돌, rejected이면 승인 불가.
7. A 삭제 후 같은 과거 보고 재전송은 보존된 receipt로 끝난다. 새 B에 과거 보고가 자동 배정되지 않는다.

## 확인 수준

위 예제와 15의 청해호 15단계는 서로 다른 시험이다. 로컬 계약 예제·DEMO·HTTP·브라우저·LIVE·실제 상대 앱을 분리해 결과를 기록한다. 제공한 명령과 기대값은 구현 지시이며, 실행 전 통과로 표시하지 않는다.
