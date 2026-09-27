# 09. 시뮬레이션 기반 조언

> 현재 구현 기준: 2026-09-27. [목록](README.md) · [실행 흐름](05-orchestration.md)

## 1. 사용자 목적과 입력

현재 조건과 변경 가정의 대응 대안을 비교한다. 채팅에서 ‘시뮬레이션 조언’을 선택하고 질문과 가정을 함께 입력한다.

```json
{
  "prompt":"현재 조건과 변경 가정의 대응안을 비교해줘",
  "kind":"simulation",
  "assumptions":"지원 자원 한 척을 사용할 수 없다고 가정",
  "request_id":"simulation-example-01"
}
```

prompt는 최대 8,000자, assumptions는 필수이며 최대 3,000자다. 단순 분석은 kind=analysis, assumptions=''로 정규화한다.

## 2. 실행·저장

별도 Simulation 테이블을 만들지 않고 Run의 kind/assumptions/based_on_version으로 구분한다. 사용자 Message에도 kind·가정을 남긴다. 기본 흐름은 plan → 필요한 요원 병렬 → critic → final이다.

모델에 update={}를 지시하고, Engine은 simulation의 update를 실제 적용하지 않는다. Store.apply_update를 직접 호출해도 simulation은 거절한다. 두 경계에서 facts·incident 오염을 막는다.

기준 버전은 실제 실행 시작 때의 현재 세션 버전이다. 큐에 있을 때 사실이 바뀌었다면 접수 당시 버전을 그대로 사용하지 않는다. 완료할 때 더 새 버전이 있으면 stale로 표시한다.

## 3. 결과가 설명할 내용

- 기준안: 현재 저장된 상태와 제약.
- 대안: 명시된 가정에서 무엇이 달라지는지.
- 비교: 기대효과·제약·불확실성과 추가 확인.
- 권고: 어떤 조건에서 해당 대안을 검토할 수 있는지.
- 근거: basis_version, report_ids, evidence_ids, assumptions.

현재 결과는 공통 Report의 summary/findings/recommendation/uncertainties에 비교 문장을 담는다. alternatives 배열이나 구조화된 점수·비교표는 없다. DEMO도 이 형식을 쓰며 규칙 기반 비교임을 밝힌다.

## 4. 사실과 가정의 경계

simulation 사용자 메시지는 evidence_for의 신고 원문 근거에서 제외하고 최종 원문 timeline에서도 제외한다. history에는 시뮬레이션 대화가 존재할 수 있으므로 kind·assumptions 구분을 유지한다. 가정이 사실로 승격되었다고 설명하지 않는다.

자산 사용 불가 가정을 검토해도 실제 assets.status는 바꾸지 않는다. AI의 미래 수치·위치·피해 예측을 새 현장 보고로 저장하지 않는다. 사용자가 대안을 채택했다는 전용 상태·계획 확정 UI는 없다.

## 5. 현재 한계

- 물리 표류 모델·실제 구조 성공률·거리/ETA 계산 없음.
- 적합한 과거 simulation을 자동 탐색·재사용하는 기능 없음.
- 모델의 비교 형식에 대한 전용 엄격 스키마 검사는 없음.
- plan이 tasks=[]와 질문만 반환하면 직접 receipt 경로가 실행될 수 있다. 이 경우 별도 가정 비교가 수행되었다고 보장할 수 없다.
- 현재 직접 receipt는 assumptions=''로 생성한다. 원래 가정은 Run·사용자 Message에 남지만 최종 Report의 가정 표시 일관성은 개선 대상이다.

## 6. 수용 사례

1. facts.total=8인 세션에서 ‘10명이라고 가정’을 요청 → 사실 총원은 8 유지, 가정은 simulation에만 표시.
2. A의 simulation 완료 후 B의 자료·보고·장부 변화 없음.
3. 실행 중 실제 facts 수정 → 결과는 이전 기준임을 표시하고 현재 장부 유지.
4. 빈 assumptions → 400, run 생성 없음.
5. 모델이 update를 반환해도 simulation에서 현재 장부 변경 없음.
6. API 실패 → failed와 원문·가정 보존, 완료 비교안 생성 없음.
7. 후속 구현에서 비교 결과가 없다면 ‘검토 미완료’로 설명하고 일반 설명을 물리 시뮬레이션 결과로 표시하지 않음.
