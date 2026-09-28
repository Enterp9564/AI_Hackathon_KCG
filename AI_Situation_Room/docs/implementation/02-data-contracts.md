# 02. 저장 데이터 계약

> 임시 프로젝트명: **HAEON(해온)** · 해양경찰 멀티에이전트 의사결정 지원 시스템. [명칭·소개 기준](../PROJECT_NAMING.md) (2026-09-27). ‘AI 오케스트라’는 협업 방식의 설명이며 이름에 포함하지 않는다.

> 현재 구현 기준: 2026-09-27. [목록](README.md) · 구현: [store.py](../../prototype/store.py)

## 1. DB 스키마와 공통 규칙

```sql
CREATE TABLE sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE objects (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  kind TEXT NOT NULL, created REAL NOT NULL, data TEXT NOT NULL
);
CREATE INDEX objects_session ON objects(session_id,kind,created);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
```

실제 초기화는 `IF NOT EXISTS`를 사용한다. DB는 WAL, 연결별 `foreign_keys=ON`, 연결 timeout 10초다. Store의 RLock과 짧은 트랜잭션으로 같은 프로세스의 접근을 직렬화한다. 외부 API를 DB 락 안에서 호출하지 않는다. 전용 스키마 마이그레이션 버전은 없다.

JSON은 `ensure_ascii=False`, `allow_nan=False`. 생성 ID는 UUID4 hex 문자열이다. `created_at`·`updated_at`·실행 시간은 Unix 초(float)이며 브라우저에서 ×1000해 표시한다. 신고자가 말한 시각은 별도 문자열 `incident.report_time`이다.

`objects`의 모든 객체에는 `id`, `session_id`, `created_at`을 넣는다. `created` 열과 최초 `created_at`은 같은 값이고 조회는 `created,id` 오름차순이다. 연결 관계는 JSON 안의 ID로 관리하며 run/task 참조에 별도 SQL 외래키는 없다.

## 2. Session

```json
{
  "id":"session-example", "title":"가상 훈련", "mode":"demo",
  "version":0, "facts":{}, "weather":null,
  "created_at":1790463600.0, "updated_at":1790463600.0
}
```

- `title`: 공백 제거 후 사용, 입력은 비어 있지 않은 문자열, 최대 80자.
- `mode`: `demo|live`. 기존 세션 모드 변경 API는 없다.
- `version`: 0부터 시작하는 정수. 장부 변경·수동 facts 저장·기상 저장에서 증가한다.
- `facts`: total/rescued/remaining/location/lat/lon/notes. 상세는 04.
- `incident`: 최초에는 생략. 이후 vessel/report_time/roster/patients/assets/distribution/conditions를 담는다.
- `facts_source`: 상황 갱신 때 넣는 사람이 읽을 수 있는 출처 표시.
- `weather`: null 또는 12의 기상 객체.

## 3. Message (`kind=messages`)

- 공통 필드 외 `role`: `user|commander`, `content`: 원문 또는 최종 summary, `run_id`, `kind`: `analysis|simulation`.
- 사용자 메시지는 `assumptions`를 함께 저장한다. 후속 정정으로 이전 `content`를 덮어쓰지 않는다.
- 최종 상황실장 메시지는 `report`, `status`, `based_on_version`을 함께 저장한다.
- 실패한 run에는 사용자 메시지가 남고, final이 없으면 상황실장 메시지를 만들지 않는다.

## 4. Run (`kind=runs`)

```json
{
  "id":"run-example", "session_id":"session-example", "created_at":1790463600.0,
  "request_id":"client-unique-id", "prompt":"현재 상황을 정리해줘",
  "kind":"analysis", "assumptions":"", "mode":"demo",
  "status":"queued", "based_on_version":0,
  "started_at":null, "ended_at":null, "decision":null, "final":null, "error":null
}
```

- `request_id`: 클라이언트 중복 방지 ID, 최대 120자. 같은 세션 안에서 비교한다.
- `prompt`: 필수, 최대 8,000자. `assumptions`: simulation일 때 필수, 최대 3,000자.
- `decision`: plan 응답. summary/questions/dispatch_orders/update/tasks를 담는다.
- `final`: 공통 Report에 report_ids/basis_version/assumptions와 경우에 따라 timeline을 추가한다.
- 장부 갱신 시 `update_applied=true`, `applied_patch`, `source_id`를 추가한다.
- `based_on_version`은 접수 시 저장하고 실행 시작 시 최신 세션 버전으로 갱신한다. 자신의 장부 갱신 후에도 새 버전으로 갱신한다.

상태: `queued → running → completed|failed|stale`. 재시작 시 미완료는 `interrupted`. 완료 뒤 새로운 상황이 저장되면 snapshot에서는 `stale`로 보인다. `stale`을 자동 재실행하지 않는다.

## 5. Task (`kind=tasks`)

필드: 공통 ID·소속·시각 + `run_id`, `role`, `instruction`, `reason`, `based_on_version`, `status`, `started_at`, `ended_at`, `report`, `error`.

`role=intel|sar|resource|critic`. `assigned`로 저장한 뒤 슬롯을 얻으면 `running`, 결과 저장 시 `completed`, 오류 시 `failed`. 재시작 복구에서는 `assigned|running`을 `interrupted`로 바꾼다. 완료 결과의 기준 버전이 달라지면 snapshot 표시가 `stale`이다.

Report에는 `summary` 문자열, `findings` 문자열 배열, `recommendation` 문자열, `uncertainties` 문자열 배열, `evidence_ids` 문자열 배열이 필수다. `information_requests`, `dispatch_orders`는 생략 가능하며 08의 구조를 사용한다. 별도 reports 테이블은 없다. final의 `report_ids`는 Task ID를 가리킨다.

## 6. Event (`kind=events`)

필수 `type`, `label`; 필요 시 `run_id`, `task_id`, `source_id`, `before`, `after`, `patch`, `version`, `information_requests`, `dispatch_orders`, `previous_weather`를 저장한다.

현재 type: `received`, `progress`, `facts_updated`, `incident_updated`, `attachment`, `weather`, `weather_failed`, `weather_invalidated`, `external_review`, `final`. 일반 임무 단계는 `progress`의 label과 참조 ID로 구별한다. 이벤트 기록은 실행 추적이며 내부 추론 원문이 아니다.

## 7. Attachment와 Call

Attachment: 공통 필드 + `name`, `content`, `summary`, `source`. CSV summary는 `{total,rescued}`, TXT/MD는 `{}`다. 파일 자체의 별도 경로 대신 본문을 DB에 저장한다.

Call: 공통 필드 + `run_id`, `role`, `stage`, `requested_model`, `reasoning_effort`, `mode`, `status`, `started_at`, `ended_at`. 성공 시 `model`, `usage`, `response_id`를 추가한다. `stage=plan|report|final`. 실패 시 성공 메타데이터가 없을 수 있다. 비밀키·Authorization 헤더는 저장하지 않는다.

## 8. Snapshot과 설정

`{session,messages,runs,tasks,events,attachments,calls,server_time}` 객체를 반환한다. 각 컬렉션은 해당 세션만 포함한다. 페이지네이션은 없다. 완료된 runs/tasks/messages의 기준 버전이 현재와 다르면 반환 객체의 status를 stale로 바꾸며, 이 조회만으로 원본 DB 객체를 다시 저장하지 않는다.

`settings`에는 `key=pinned`, `value=<session ID>` 한 행으로 전체 상황판 고정 세션을 보존한다. 브라우저별 설정이 아니다. 고정 세션 삭제 시 이 행도 삭제한다.

## 9. 버전·영속성 수용 기준

- facts·incident는 정확히 검증된 트랜잭션만 반영하고 실패하면 해당 트랜잭션 전체를 되돌린다.
- 보고가 S1 기준인데 현재 S2이면 이전 상황 기준 표시를 한다.
- 첨부·고정·채팅 접수 자체는 상황 version을 증가시키지 않는다. 첨부 변경만으로 기존 보고가 stale이 되지는 않는 현재 한계가 있다.
- 다른 세션 객체를 특정 session_id와 함께 조회하면 거절한다. 전체 snapshot은 다른 세션의 정보를 포함하지 않는다.
- 동일 ID로 재접수해도 원문·run을 중복 생성하지 않는다. 상세는 03·05.

## 2026-09-27 추가: 외부 보고 출처

`incident_links`와 `inbox_reports` 스키마는 [16](16-external-inbox.md)이 소유한다. 기존 run·사용자 메시지·직접 인용 결과에는 nullable `external_report_id`를 추가했다. 외부 근거를 사용한 후속 최종 보고와 commander 메시지는 `external_report_ids` 목록을 가진다. 일반 장부 추출에는 이 출처가 있는 요약을 넣지 않는다. 기존 데이터에 필드가 없으면 일반 사용자 입력으로 취급한다.
