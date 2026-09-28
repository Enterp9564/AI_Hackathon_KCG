# 15. 검증과 인수 기준

> 임시 프로젝트명: **HAEON(해온)** · 해양경찰 멀티에이전트 의사결정 지원 시스템. [명칭·소개 기준](../PROJECT_NAMING.md) (2026-09-27). ‘AI 오케스트라’는 협업 방식의 설명이며 이름에 포함하지 않는다.

> 2026-09-27 문서화. 아래는 시험 설계이며 새로 실행한 결과가 아니다. 실제 결과는 [PROGRESS](../../prototype/PROGRESS.md)에 날짜별로 기록한다. [목록](README.md)

## 1. 시험 층위

- 단위: 저장·장부·실행·모델 요청 형식, 임시 DB와 DEMO/mock 사용.
- HTTP: 실제 로컬 서버와 JSON 경로·토큰·응답 상태. 포트 바인딩 권한 필요.
- 브라우저: 키보드·세션 전환·삭제·상황판·상태·레이아웃. JS 문법 검사를 UI 통과로 쓰지 않음.
- LIVE: 실제 외부 모델/기상 호출. 모델 설정·응답·오류·시각·사용량과 수용 정답 확인.
- 저장 결과 재검사: 기존 실행 JSON을 검사. 새 LIVE 실행이나 현재 코드 전체 검증이 아님.

## 2. 기존 명령

프로젝트 루트에서 실행한다.

```sh
python3 -m unittest prototype.tests.test_engine prototype.tests.test_incident prototype.tests.test_models prototype.tests.test_store -q
node --check prototype/static/app.js
python3 -m unittest discover -s prototype/tests -q
```

2026-09-28 소스에서 test_ 메서드를 정적으로 집계하면 앞의 핵심 단위 39개 + inbox 12개 = 네트워크 없는 Python 단위 51개, HTTP 4개 + MCP HTTP 4개 = 총 59개다. 이는 현재 정의 수이며 오늘 실행 통과를 뜻하지 않는다. 이전 42개 기록은 MCP 추가 전 구성이다. JS 공유 전송과 브라우저 검사는 별도다.

저장 파일이 있는 로컬 환경에서만:

```sh
python3 prototype/scenarios/check_saved_run.py prototype/runtime/cheonghae-live-test-v3.json
```

배포본에는 runtime 파일이 없을 수 있다. 없으면 ‘시험 자료 없음’으로 기록한다. 결과를 만들어 채우지 않는다.

## 3. 핵심 단위 수용 사례

1. 세션 격리: A/B 인원·첨부·run이 섞이지 않고 Store 재열기 후 유지.
2. 멱등 접수: 동일 request_id·내용으로 한 run/원문, 다른 내용은 충돌.
3. 장부: 이름 정정 속성 보존, distribution 전체 교체, 재이송 누계 유지, 잘못된 합계 전체 거절.
4. 버전: 오래된 갱신안 거절, 완료 보고의 stale 표시, 위치 변경 기상 해제.
5. 실행: 독립 요원의 실제 시각 중첩, 선택 역할만 호출, critic→final 순서, 미래 큐 원문 제외.
6. 실패: provider 실패는 run.failed, 입력 보존, DEMO fallback 없음.
7. simulation: 가정 필수, facts/incident 변경 차단, 다른 세션 불변.
8. 모델 계약: 실제 요청 model/medium/store=false, 완료하지 않은 응답·잘못된 JSON 거절.
9. 근거: 공통 매뉴얼 제공, simulation 원문 제외, 다른 세션/미제공 ID 인용 차단.
10. 삭제·재시작: 작업 중 삭제 거절, 완료 후 소속 기록·고정 제거, 중단 작업 interrupted.

기존 시험 소유 파일은 [tests](../../prototype/tests/test_engine.py)의 test_engine/test_incident/test_models/test_store다. 기상 네트워크의 모든 오류·UI 동선·의미 기반 질문 선정이 이 39개에 포함되어 있다고 주장하지 않는다.

## 4. HTTP 수용 사례

현재 test_http 4개는 악성 Origin·잘못된 토큰 거절, 세션 입력·snapshot의 무작업, message 왕복·중복 접수·없는 monitor 쓰기 경로, 수신함 로컬 승인/세션 경계를 확인한다. test_mcp 4개는 handshake/도구/멱등 수신, 인증/Origin/Host/버전, project/입력, 알림의 제출 금지/충돌 보존을 확인한다.

추가 인수 시에는 facts 버전 충돌, CSV 오류, weather 실패/동시 수정, 진행 중 삭제·고정 세션 삭제, 잘못된 Host·본문 크기를 별도로 시험한다. 기존 HTTP/MCP 8개가 이 전체를 포괄하지 않는다.

## 5. 브라우저 수용 절차

별도 시험 DB와 가상 세션을 사용한다. 실행 브라우저·해상도·일시를 기록한다.

1. 키 유무에 따른 새 세션 LIVE/DEMO 선택, 기존 DEMO 유지.
2. Enter·Shift+Enter·한글 조합, 전송 직후 접수·상단 진행.
3. 전송 실패 후 초안 보존·같은 ID 재시도·중복 run 없음.
4. A 실행 중 B로 전환, 초안·늦은 보고·늦은 snapshot 격리.
5. 질문 이유·출처, 출동안 후보 상태, 추가 펼침, 근거·원문 상세.
6. 이름 정정·환자 분할·총원 불일치·이전 상황 표시.
7. 삭제 취소·진행 중 거절·마지막 세션 삭제·다른 탭 삭제 반영.
8. A 고정/B 작업, 고정 변경·삭제, 전체화면·복귀.
9. 연결 10초/30초 지연, 상세 dialog의 열람시점 표시.
10. 1920×1080·좁은 화면·모션 감소, 긴 보고·원거리 가독성·2시간 내구성.

## 6. 청해호 15건의 정답

원문 입력 순서는 [cheonghae-fire.md](../../prototype/scenarios/cheonghae-fire.md)를 그대로 사용한다. 각 요청이 끝난 뒤 다음을 보내는 새 LIVE 수용 시험과 기존 저장 결과 검사를 구분한다.

- 2단계: total=7, rescued=0, remaining=7.
- 5단계: 8, 0, 8.
- 7단계: 8, 3, 5.
- 9단계: 8, 6, 2.
- 12·15단계: 8, 8, 0.
- 11단계 이름 정정: 이기란→이기관, 동일 ID와 나머지 인물 속성 보존.
- 최종 분포: 301함 5, 묵호항 3, 청해호·동진호 잔류 0. 합계 8.
- 동진호 own_crew=3은 대상자 총원과 별도. 지원 종료 기록 유지.
- 환자 합계 3: 묵호항에서 화상 1·연기흡입 1 구급대 인계 완료, 301함의 다른 연기흡입 1은 진료 예정.
- 최종 report_time=14:50, 기관실 잔류 열기·침수 의심·예인 대기를 확실성 그대로 유지.
- 최종 timeline은 신고·정정 원문 전체를 접수순으로 보존. 실패 후 재요청 원문도 남김.

기존 check_saved_run은 11단계 report_ids=[]도 검사한다. 이는 당시 ‘단순 정정 직접 처리’ 구현의 수용 조건이다. 최신 요원 우선 배정 구조로 바꿀 때는 이 항목을 새 요구에 맞춰 재설계하고 과거 판정은 보존해야 한다.

## 7. 역사적 결과와 현재 판정

- [최초 LIVE](../../prototype/scenarios/cheonghae-test-results.md): 15건·85회 호출, API 완료였지만 장부·정정 수용 실패.
- [개선 LIVE](../../prototype/scenarios/cheonghae-improvement-results.md): 9단계 오류 차단·수정·재실행 후 최종 PASS, 실패 포함 46회 호출.
- 2026-09-26: 단위 39개·JS 문법·기존 v3 저장 검사 PASS. 당시 새 HTTP·브라우저·기상·LIVE 전체 재실행 없음.

최신 medium·매뉴얼·UI 설정에서 새 무중단 LIVE 결과는 별도로 필요하다. A호 발표 예시 5→7명과 청해호 시험 7→8명을 섞지 않는다.

## 8. 새 결과 기록 양식

날짜/코드 기준, 실행 명령·입력, 모드·모델·effort, 임시 DB/산출물 위치, 기대값, 관측값, PASS/FAIL/미실시, 실패·수정·재실행 경과를 남긴다. 키·원본 환경값은 쓰지 않는다. 단위·HTTP·브라우저·LIVE 각 줄을 구별한다.

문서만 변경한 작업은 링크·JSON 예제·경로·코드 계약·변경 범위를 검사한다. 앱 시험을 실행하지 않았다면 과거 통과 기록을 이번 통과 기록으로 옮기지 않는다.

## 9. 2026-09-28 재구현 시험 이름 목록

아래는 현재 소스의 시험 식별자다. 구현하는 기능의 테스트부터 만들고 기대값은 해당 명세와 21의 계약 예제를 따른다. 이름이 존재하는 것과 시험 통과/완전한 커버리지는 다르다.

### test_engine.py

- `EngineTests.test_parallel_reports_final_and_separate_memory`
- `EngineTests.test_simulation_advice_keeps_facts_and_assumptions`
- `EngineTests.test_duplicate_submission_does_not_execute_twice`
- `EngineTests.test_change_during_execution_marks_old_report`
- `EngineTests.test_provider_error_is_not_success_or_demo_fallback`
- `EngineTests.test_simple_information_request_only_assigns_information`
- `EngineTests.test_commander_can_request_missing_information_without_assigning_agents`
- `EngineTests.test_specialist_information_request_is_forwarded_to_user`
- `EngineTests.test_fire_report_creates_manual_dispatch_orders`
- `EngineTests.test_queued_followup_receives_previous_final_and_no_future_input`
- `EngineTests.test_one_session_backlog_does_not_block_other_session`

### test_http.py

- `HTTPTests.test_origin_and_write_token_enforced`
- `HTTPTests.test_session_input_and_snapshot_do_not_create_jobs`
- `HTTPTests.test_message_roundtrip_and_monitor_write_rejected`
- `HTTPTests.test_inbox_local_approval_and_session_guard`

### test_inbox.py

- `InboxTests.test_receipt_only_and_original_preserved`
- `InboxTests.test_reception_idempotency_and_conflict`
- `InboxTests.test_unknown_incident_and_source`
- `InboxTests.test_defer_reject_history`
- `InboxTests.test_wrong_session_and_concurrent_approval`
- `InboxTests.test_queue_full_rolls_back_approval`
- `InboxTests.test_restart_retains_dedup_and_deleted_session_does_not_reroute`
- `InboxTests.test_quote_cannot_apply_facts_even_if_model_requests_update`
- `InboxTests.test_later_plan_does_not_treat_quote_as_user_fact`
- `InboxTests.test_approval_and_reject_race_has_one_terminal_outcome`
- `InboxTests.test_live_agents_use_refreshed_facts`
- `InboxTests.test_external_provenance_survives_followup_summaries`

### test_incident.py

- `IncidentTests.test_patch_preserves_name_identity_and_other_attributes_and_audit`
- `IncidentTests.test_transfer_does_not_inflate_rescued_and_persists`
- `IncidentTests.test_invalid_sum_rejects_whole_transaction`
- `IncidentTests.test_simulation_cannot_mutate`
- `IncidentTests.test_idempotency_version_and_separate_session`
- `IncidentTests.test_unknown_fields_and_wrong_types_rejected`
- `IntakeFlowTests.test_intake_persists_before_analysis_and_simple_update_skips_specialists`
- `IntakeFlowTests.test_original_reports_are_citable_and_simulation_not_evidence_fact`
- `IntakeFlowTests.test_basic_manual_and_force_catalog_are_always_available_as_evidence`
- `ManualIncidentTests.test_manual_note_edit_preserves_remaining_and_rejects_bad_total`
- `ManualIncidentTests.test_receipt_never_cites_missing_facts`
- `ManualIncidentTests.test_explicit_leading_report_time_is_saved_without_model_guess`
- `ManualIncidentTests.test_name_correction_updates_derived_notes_but_keeps_original_message`
- `ManualIncidentTests.test_final_report_keeps_full_original_timeline`
- `ManualIncidentTests.test_distribution_is_complete_snapshot_not_additive_places`

### test_mcp.py

- `MCPTests.test_handshake_tools_and_idempotent_receipt`
- `MCPTests.test_auth_origin_host_and_protocol`
- `MCPTests.test_project_identity_and_invalid_arguments`
- `MCPTests.test_notification_cannot_submit_and_conflict_preserves_original`

### test_models.py

- `ModelContractTests.test_actual_request_uses_role_effort_and_session_input`
- `ModelContractTests.test_incomplete_or_refusal_response_is_not_report`

### test_store.py

- `StoreTests.test_facts_are_separate_and_survive_reopen`
- `StoreTests.test_retries_create_one_run_and_message`
- `StoreTests.test_version_conflict_and_invalid_counts_do_not_write`
- `StoreTests.test_attachment_and_run_cannot_cross_sessions`
- `StoreTests.test_simulation_requires_assumptions_and_does_not_change_facts`
- `StoreTests.test_missing_session_rejected`
- `StoreTests.test_delete_session_removes_records_and_pinned_setting`
- `StoreTests.test_delete_session_rejects_running_work`
- `StoreTests.test_location_change_clears_old_place_weather`
- `StoreTests.test_restart_marks_unfinished_runs_interrupted`
- `StoreTests.test_completed_report_becomes_stale_after_later_correction`
