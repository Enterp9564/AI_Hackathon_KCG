# 검증요원 ON/OFF Implementation Plan

> 실행 상태: 2026-09-30 후속 승인으로 구현·8860 적용 완료. 아래는 작성 당시 계획이며 실제 검증·차이는 [수신 구현](../../implementation/35-linkone-current-state.md) 및 [검증 설정 구현](../../implementation/36-critic-toggle.md)을 따른다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 현재 요청은 계획 작성만이며 구현·개발 보조 에이전트 생성·커밋·푸시를 시작하지 않는다.

**Goal:** 설정에서 별도 검증요원을 켜거나 끄고, OFF이면 전문요원 보고 후 상황실장이 바로 종합하도록 한다.

**Architecture:** SQLite 설정을 새 run 접수 트랜잭션에서 고정하고 Engine이 그 값에 따라 검증 단계를 분기한다. UI는 전역 설정과 개별 실행의 실제 검증 상태를 구별한다.

**Tech Stack:** 기존 Python HTTP·SQLite·HTML/CSS/JavaScript.

**Spec:** [가능성·설정·실행·표시 계약](../specs/2026-09-30-critic-toggle-design.md).

## Global Constraints

- 미설정 기본값 ON. 서버 DB 단위 저장, 다음 새 요청부터 적용, 기존 진행·대기 요청 유지.
- OpenAI·로컬 LLM·DEMO에 동일 분기. 설정 저장은 모델 호출·새 분석을 생성하지 않는다.
- OFF는 별도 검증요원 호출만 생략. 상황실장 종합·코드의 근거/형식 검사·세션 격리 유지.
- 검증 실패 시 OFF 자동 전환 금지. 과거 task/call/report 수정 금지.
- 상시 부하 측정·자동 벤치마크·새 LIVE 성능 시험은 이 계획의 범위 밖이다.

## Review Focus

1. 대기 중 ON 요청을 OFF로 변경해도 이미 접수된 요청의 설정은 보존(Task 1·2).
2. Link-One 선접수 및 MCP 인용도 동일한 최초 접수 시점에 설정 고정(Task 1).
3. OFF 실행이 화면에서 검증 대기에 멈추거나 완료로 표시되지 않음(Task 3).
4. 검증요원 없는 직접 처리·전문요원 실패·과거 필드 누락을 OFF 생략과 구분(Task 2·3).
5. 설정 저장 실패·중복 전송·서버 재시작에도 사용자 선택과 실행 기록 일치(Task 1·3).

## 변경 파일과 책임

| 파일 | 책임 |
|---|---|
| prototype/store.py | critic 설정 읽기/저장, 최초 `_enqueue` 시 run에 고정 |
| prototype/engine.py | 설정 API용 메서드, 실행 분기·검증 상태·종합 문맥 |
| prototype/server.py | critic 설정 GET/POST, 부트스트랩 설정 응답 |
| prototype/models.py | OFF 최종 종합용 짧은 조건부 지침 |
| prototype/static/model-settings.js | 검증요원 스위치·저장/실패 복원 |
| prototype/static/app.js | 진행 단계·검증 생략·최종 상세·과거 실행 표시 |
| 신규 prototype/tests/test_critic_toggle.py | 저장·접수·엔진·가짜 모델 계약 |
| 신규 prototype/tests/test_critic_toggle_http.py | HTTP boolean·보호·설정 지속 |
| 신규 prototype/tests/test_critic_toggle_ui.cjs | 단계 전환·스위치·과거 실행 표시 |
| docs/implementation/25-focused-critic.md, 10-operator-ui.md, 23-prompt-reference.md, 13, PROGRESS | 구현 후 실제 동작·검증·운영 설명 |

## Task 1: 설정 저장·API·접수 시 고정

**Interfaces**
- `Store.critic_settings() -> dict`: `{enabled, scope:"server", applies_to:"new_requests"}`. 값이 없으면 enabled=true.
- `Store.set_critic_enabled(enabled: bool) -> dict`: 정확한 boolean 검사 후 기존 settings 테이블에 저장.
- `Engine.critic_settings()` / `Engine.configure_critic(data)`는 위 저장 계약을 제공한다. 설정 변경 때문에 현재 실행을 취소하거나 전체 작업 완료를 기다리지 않는다.
- `GET/POST /api/settings/critic`, 부트스트랩 응답 `critic`. POST 성공 200, 잘못된 값 400, 기존 인증/출처 오류 계약 유지.
- `Store._enqueue`는 중복 request_id 확인 후 같은 SQLite 트랜잭션에서 설정을 읽고 새 run에 `critic_enabled`와 `critic_review={status:"pending"}`를 저장한다. 이미 존재하는 run에는 설정을 재적용하지 않는다.

- [ ] `test_default_on_and_setting_persists`: 빈 DB ON, OFF 저장·Store 재생성 후 OFF, 별도 DB는 ON. 문자열/숫자/null 거부를 확인한다.
- [ ] `test_capture_policy_for_all_submission_paths`: 일반 채팅·MCP 인용·Link-One 전체 동기화/재분석의 실제 접수 경로에 fake source를 주입해 새 run의 설정을 확인한다. 설정 변경 전에 생성된 run은 유지한다.
- [ ] `test_duplicate_request_keeps_original_policy`: ON 접수 → OFF 변경 → 같은 request_id 재전송 시 run·메시지가 추가되지 않고 원래 ON인지 확인한다.
- [ ] 새 시험 실패를 확인한다: `python3 -m unittest prototype.tests.test_critic_toggle -v`.
- [ ] Store·Engine·서버 인터페이스를 구현한다. `Engine.submit`의 model_config 저장이 critic 설정을 덮어쓰지 않게 한다. Link-One의 `_enqueue` 후 submit 사이에 설정이 바뀌어도 최초 값을 유지한다.
- [ ] HTTP 시험에서 GET/POST·재시작 지속·잘못된 boolean·Host/Origin/토큰 보호를 확인한다: `python3 -m unittest prototype.tests.test_critic_toggle prototype.tests.test_critic_toggle_http -v`.

## Task 2: 실행 분기·기록·최종 종합

**Interfaces**
- `run.get('critic_enabled', True)`를 해당 실행의 고정 정책으로 사용한다.
- `critic_review.status`: pending / running / completed / failed / skipped / not_applicable. skipped 이유는 disabled_by_setting. 서버가 저장하며 모델 출력으로 덮어쓰지 않는다.
- 최종 호출 문맥 `review_policy={critic_enabled:bool, critic_status:str}`. OFF 지침은 commander/final에만 추가한다.

- [ ] `test_off_skips_call_and_preserves_commander_final`: 전문요원 배정이 있는 deterministic fake model에서 OFF일 때 critic task/call/report/context 기록 0건, commander/final 1회, skipped 이벤트 1건을 확인한다. ON일 때 기존 검증 1회와 순서를 확인한다.
- [ ] `test_toggle_during_run_and_queue_preserves_captured_policy`: 이벤트 장벽을 가진 fake model로 ON 실행·ON 대기 요청 접수 후 OFF 저장, 새 OFF 요청 접수. 앞의 두 요청은 ON, 마지막은 OFF인지 확인한다. 시간 sleep에 의존하지 않는다.
- [ ] `test_direct_receipt_and_failure_are_not_successful_review`: 직접 처리 not_applicable, 전문요원 실패 시 최종 종합 미실행, ON 검증 실패 시 failed·자동 OFF 없음, 과거 필드 없는 run의 ON 호환을 확인한다.
- [ ] `test_off_retains_evidence_validation`: fake model의 잘못된 근거 ID/형식이 OFF에서도 기존 검사에 실패하는지 확인한다.
- [ ] 새 테스트 실패 확인 후 `Engine.process`의 검증 호출 부분을 분기하고 서버 이벤트/상태를 저장한다. OFF에서는 기존 reports만 최종 종합에 제공한다. 이력에 가짜 검증 report ID를 넣지 않는다.
- [ ] models.py에서 OFF 최종 종합용 짧은 지침을 추가한다. 검증 전체 프롬프트·별도 모델 호출은 추가하지 않는다. 테스트가 최종 입력의 실제 reports와 review_policy를 검사하도록 한다.
- [ ] `python3 -m unittest prototype.tests.test_critic_toggle prototype.tests.test_critic_load prototype.tests.test_models -v`로 ON 회귀·OFF 계약을 확인한다. LIVE API 호출은 하지 않는다.

## Task 3: 설정 스위치·실행 화면·이력

**Interfaces**
- 기존 `openModelSettings()`에서 critic 설정을 함께 읽고 `criticToggle` 체크박스 스위치와 `criticStatus` 안내를 표시한다. 모델 폼 저장과 독립적으로 POST한다.
- `criticReviewState(run, tasks)` 순수 JS 함수: 새 run은 저장된 상태, 이전 run은 실제 critic task 상태와 직접 처리 여부로 표시를 결정한다. 근거 부족은 unknown.
- `executionPhase`, `progressState`, `renderFlow`, `openFinal`은 같은 상태 함수를 사용한다. OFF 전문요원이 모두 완료되면 synthesis, 선행 실패가 있으면 stopping이다.

- [ ] `test_off_goes_from_specialists_to_synthesis`: OFF에서 검증 대기/검증 중/검증 완료 문구가 나타나지 않고 ‘검증요원 생략 · 설정 OFF’가 표시되는지 확인한다. 실패 우선순위도 검증한다.
- [ ] `test_history_uses_run_policy_not_current_setting`: 현재 OFF여도 과거 ON 검증 보고는 보존, 현재 ON여도 과거 OFF는 생략 표시. 필드 없는 과거 실행은 task 증거를 따르며 기록 부족은 미확인인지 확인한다.
- [ ] `test_toggle_failure_restores_value_and_preserves_draft`: 저장 성공·오류 복원·모달 닫힌 뒤 응답 처리·중복 클릭 방지·초안과 모델 입력 보존을 확인한다.
- [ ] 위 시험 실패 확인 후 스위치와 단계 표시를 구현한다. final 상세와 시간축도 실제 실행 이력에 일치시킨다.
- [ ] `node --test prototype/tests/test_critic_toggle_ui.cjs`와 기존 UI 회귀를 실행한다. 격리 브라우저에서 ON/OFF 각각 한 번의 DEMO 흐름을 확인한다.

## Task 4: 통합 확인·문서·적용

- [ ] Python 전체·JS 전체·문법·diff 검사를 실행하고 실패를 수정한다. 실제 LLM 미호출 시험과 향후 LIVE 시험을 구분해 기록한다.
- [ ] 알림 2초/상태 3초 변경과 함께 적용해도 자동 수신이 AI 호출이나 설정 변경을 발생시키지 않는지 fake source/model로 확인한다.
- [ ] 기존 설정이 없는 DB의 기본 ON과 기존 OFF 선택의 재시작 지속을 확인한다. 운영 적용 시에는 서버별 DB·모델·SAR 옵션을 보존한다.
- [ ] 관련 상세 문서·13·PROGRESS에 실제 구현·시험 결과를 기록한다. 현재 계획 작성 단계에서는 코드 변경·설정 저장·재시작·커밋·푸시를 하지 않는다.

[알림 2초·현재 상태 3초 고정 수신 계획](2026-09-30-linkone-current-state-polling.md)
