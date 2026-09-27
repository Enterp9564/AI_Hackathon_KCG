# 04. 신고·정정·현재 장부

> 현재 구현 기준: 2026-09-27. [목록](README.md) · 구현: [incident.py](../../prototype/incident.py), Store.apply_update / set_facts

## 1. 상태 구조

`session.facts`는 집계·대표 위치, `session.incident`는 세부 사건 장부다. 다음은 모델 update의 가상 예제다. update의 최상위 키가 저장 시 facts 또는 incident로 나뉜다.

```json
{
  "facts":{"total":8,"rescued":3,"remaining":5,"location":"묵호 인근","notes":"사용자 신고 기준"},
  "vessel":"훈련선", "report_time":"14:10",
  "distribution":{"훈련선":5,"지원선":3},
  "roster":{"engineer-01":{"name":"이기관","role":"기관장","location":"훈련선","condition":"부상 보고 없음","lifejacket":"착용"}},
  "patients":{"burn-01":{"kind":"화상","count":1,"location":"지원선","status":"이송 예정"}},
  "assets":{"support-01":{"name":"지원선","own_crew":3,"status":"지원 중"}},
  "conditions":{"fire":"기관실 화재 신고","flooding":"침수 의심","evacuation":"일부 퇴선"}
}
```

## 2. 허용 필드·타입

- facts: total/rescued/remaining은 정수 0~100,000. bool·숫자 문자열은 거절한다.
- lat/lon은 유한한 int/float, 각각 ±90/±180 범위. bool·NaN·Infinity 거절.
- facts.location/notes, vessel/report_time, ID·장소명·문자 필드는 비어 있지 않은 문자열, 최대 2,000자.
- roster의 인물 필드: name, role, location, condition, lifejacket만 허용.
- patients의 그룹 필드: kind, count, location, status. count는 위 정수 규칙.
- assets의 자산 필드: name, own_crew, status. own_crew는 위 정수 규칙.
- distribution: 장소명 → 정수 인원. conditions: 문자열 키 → 문자열 설명.
- conditions의 권장 키는 fire/flooding/weather/tow/pollution/evacuation이나 현재 서버는 다른 문자열 키도 허용한다.
- 알 수 없는 값을 null·0으로 채우지 않고 키를 생략한다. 실제 0명이 확인된 경우만 0을 쓴다.

## 3. 병합과 교체 규칙

1. 기존 세션을 깊은 복사한다. 원본을 직접 수정하지 않는다.
2. facts·conditions는 전달한 키만 병합한다.
3. roster/patients/assets는 안정적인 ID를 기준으로 해당 필드만 병합한다. 생략된 ID·필드는 유지된다. 삭제 연산은 없다.
4. **distribution이 전달되면 전체 분포를 교체한다.** 현재 인원이 남은 모든 장소를 포함해야 한다. 이동 완료한 장소는 생략하거나 0으로 넣는다.
5. 이름 정정은 동일 ID의 name만 바꾼다. 기존 직책·위치·건강·구명조끼를 보존한다. 파생 facts.notes의 기존 이름도 단어 경계에 맞는 경우 치환한다. 원문 메시지는 수정하지 않는다.
6. 신고 맨 앞에 유효한 `HH:MM`이 있으면 apply_update에서 report_time에 반영한다. 전체 날짜·시간대 파싱이나 자유형 시각 검증은 없다.

예: `{ "roster":{"engineer-01":{"name":"이기관"}} }`은 이름만 바꾼다. `{"distribution":{"301함":5,"묵호항":3}}`은 이전 청해호·동진호 장소를 누적하지 않는다.

## 4. 저장 전 수량 검사

total이 있으면 아래를 검사한다.

- rescued와 remaining 각각이 total 이하.
- 둘 다 있으면 rescued + remaining ≤ total. 전원의 위치가 미확인일 수 있어 항상 등식으로 강제하지 않는다.
- 비어 있지 않은 distribution의 합은 total과 정확히 같아야 한다.
- 모든 patients 그룹 count 합은 total 이하.

roster 인원수=total 강제는 없다. 이름이 알려진 일부 인물만 기록할 수 있다. 위치와 인물·환자 사이의 완전한 교차 검증은 현재 없다. 지원선 own_crew는 사고 대상자 총원·구조누계에 더하지 않는다. 이미 구조된 사람의 재이송은 rescued를 증가시키지 않는다.

환자 일부가 이동하면 기존 그룹 count를 줄이고 새로운 그룹 ID로 이동 인원을 기록한다. 기존 그룹을 그대로 두고 새 그룹만 추가하면 중복 집계가 된다. 건강상태와 퇴선 의사를 같은 필드에 섞지 않는다.

## 5. apply_update의 트랜잭션

1. run과 소속 세션을 읽는다.
2. 이미 update_applied이면 같은 patch는 기존 세션 반환, 다른 patch는 Conflict.
3. simulation이면 갱신 거절. 현재 version과 expected_version이 다르면 Conflict.
4. 병합·검사·명시 시각 반영 후 이전 facts/incident와 비교한다.
5. 변경이 있으면 version+1, facts_source 갱신, session 저장. lat/lon/location 중 하나가 바뀌면 weather=null.
6. incident_updated event에 원문 source_id, run_id, before, after, patch를 남긴다.
7. run에 update_applied, applied_patch, based_on_version, source_id를 저장한다.

변경이 없으면 version·갱신 이벤트를 증가시키지 않지만 반영 여부를 run에 표시한다. 실패는 해당 트랜잭션을 전부 취소한다. 뒤의 요원 실패가 이미 성공한 장부 반영을 되돌리지는 않는다.

## 6. 수동 facts 수정은 다른 계약

POST facts의 `{version,facts}`는 patch가 아니라 **정리된 facts 전체 교체**다. 전달하지 않은 기존 필드가 사라질 수 있다. 예외로 remaining이 요청에 없고 이전에 있으면 보존한다. null/빈 문자열은 저장하지 않는다.

버전은 정확한 int여야 한다. 기존 incident는 유지하므로 새 total과 기존 분포가 다르면 거절한다. lat/lon 변경 시 기상을 해제하고 weather_invalidated 이벤트에 이전 기상을 남긴다. location 문구만 바꾼 경우의 무효화는 apply_update 경로와 다르다. 수동 저장은 같은 값이어도 version을 증가시키고 facts_updated의 before/after를 남긴다.

## 7. 사실의 확실성과 직접 반영

‘침수 의심’, ‘진료 예정’, ‘관찰되지 않음’, ‘부상 보고 없음’은 그대로 보존한다. 독립 실측이 아니라 사용자 신고라는 출처를 표시한다. 사용자 명시 정정은 원문을 근거로 반영할 수 있다.

tasks=[]인 plan은 receipt 함수로 현재 집계·분포·명부·환자·위험·자산·출동안을 설명한다. report_ids=[], basis_version, 근거 ID를 저장한다. 별도 최종 모델 호출이나 검증요원 호출은 없다. 직접 반영 보고에는 병렬 경로의 전체 timeline 필드가 없다.

## 8. 수용 기준

- 총원 7→8 정정과 분포 갱신이 함께 일관되게 저장된다.
- 지원선 3명 재이송 후 최종 301함 5/묵호항 3, 총원·구조누계 8 유지.
- 이기란→이기관 정정에서 같은 인물 ID와 나머지 속성, 과거 원문 보존.
- 합계 9인 분포를 total=8에 넣으면 전체 patch 거절, before 상태 보존.
- simulation patch, 오래된 버전 patch, 잘못된 필드·타입 거절.
- 상세 청해호 사례와 기준은 [15 검증](15-acceptance.md)을 따른다.
