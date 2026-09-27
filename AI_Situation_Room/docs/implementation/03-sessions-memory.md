# 03. 세션과 기억

> 현재 구현 기준: 2026-09-27. [목록](README.md) · [데이터 계약](02-data-contracts.md)

## 1. 사용자 흐름

새 세션에 이름과 실행 방식을 지정한다. 초기 상태는 version=0, facts={}, weather=null, 대화·첨부·실행 목록은 빈 배열이다. 세션 목록은 생성시각 최신순이다. 화면을 전환해도 이전 실행은 원래 세션에 계속 저장된다.

UI는 `/api/config.live_available`이 true이면 새 세션 LIVE를 기본 선택한다. 키가 없으면 LIVE를 비활성화한다. HTTP 세션 생성에서 mode 생략 시 기본값은 demo다. 키가 나중에 생겨도 기존 DEMO를 바꾸지 않는다.

## 2. 세션의 격리 범위

- 독립 보관: facts, incident, weather, messages, runs, tasks, events, attachments, calls.
- 공통 자료: 역할 설정, 기본 매뉴얼, 동해 카탈로그.
- 전역 설정: 고정 상황판의 session_id 한 개.
- 브라우저 메모리: 세션별 작성 중 prompt·assumptions·kind, 재시도 request_id.
- localStorage: 마지막 선택 세션 ID만 `situation-room:last-session`에 저장한다.

기억은 서버가 매번 구성하는 입력이다. 모델 API의 이전 응답 ID나 전역 대화 상태를 재사용하지 않는다. 동일 문장·동일 선명이어도 다른 세션의 명부와 첨부를 가져오면 안 된다.

## 3. 접수와 중복 방지

1. content, kind, assumptions, request_id를 검사한다.
2. 트랜잭션에서 해당 세션의 기존 runs를 검사한다.
3. 같은 request_id와 같은 정규화된 prompt/kind/assumptions이면 기존 run을 돌려준다.
4. 같은 ID에 다른 내용이면 Conflict(HTTP 409)를 반환한다.
5. 그 세션 queued/running 합계가 8개 이상이면 새 접수를 409로 거절한다.
6. 새 run·사용자 원문·received event를 같은 트랜잭션에서 저장한다.

브라우저는 동일 전송의 HTTP 응답을 못 받았을 때 같은 ID로 재전송한다. 이미 종료·실패한 run을 같은 ID로 보내도 새 실행이 되지 않는다. 재검토는 새 request_id가 필요하다.

## 4. 실행 중 이력 선택

큐에서 자기 차례가 되었을 때 최신 세션을 읽고, 접수된 runs 중 자신의 run까지의 메시지만 모은다. 나중에 접수되어 아직 처리하지 않은 요청을 현재 AI 입력에 넣지 않는다. 이전 run의 최종 보고는 다음 run이 시작할 때 이력에 들어갈 수 있다.

전체 문맥은 session/request/history/evidence다. JSON 직렬화 길이가 180,000자를 초과하면 모델 호출 전에 실패시키고 원문을 보존한다. 이후 LIVE plan은 최근 메시지 4건의 role/content와 최근 원문 근거를 사용한다. 전문요원은 history=[]와 현재 장부·최신 신고 원문·공통 근거를 받는다. 최종 종합은 보존한 근거와 보고를 받는다.

현재는 전체 문맥 크기를 줄이기 전에 한도를 검사하므로 긴 기록이 있는 세션은 최근 4건만으로도 처리 가능한 요청이 한도 오류가 될 수 있다. 자동 요약·페이지네이션·장기 기억 압축은 미구현이다.

## 5. 삭제

UI의 × → 제목을 포함한 확인 창 → 취소이면 요청하지 않음 → 확인이면 POST delete.

서버는 하나의 트랜잭션에서 세션 존재와 queued/running run을 검사한다. 작업이 남아 있으면 409로 거절한다. 삭제 가능하면 해당 세션 objects, sessions 행, 해당 pinned 설정을 삭제한다. 다른 세션과 외부 백업은 유지한다. 휴지통·되돌리기 API는 없다.

현재 선택 세션 삭제 후 UI는 선택·snapshot·localStorage를 비우고 목록을 갱신한다. 남은 세션이 있으면 기본 선택하고 없으면 빈 화면을 표시한다. 다른 탭에서 삭제된 선택 세션을 정리하는 동선은 별도 브라우저 회귀 대상으로 남아 있다.

## 6. 재시작

DB를 다시 열면 완료된 장부·원문·보고·고정 상태를 복원한다. Store.recover는 미완료 runs/tasks의 queued/running/assigned를 interrupted로 바꾸고 종료시각과 재요청 안내를 저장한다. 메모리 큐를 복원하거나 외부 API를 자동 재호출하지 않는다.

창을 닫아도 서버가 살아 있으면 작업은 계속된다. 서버 종료와 브라우저 종료를 혼동하지 않는다. 초안 Map은 브라우저 새로고침 후 보존되지 않는다.

## 7. 수용 사례

1. A=총원 5, B=총원 9 저장 후 전환·재시작해 각각 유지.
2. A에만 CSV 첨부 → B의 snapshot과 AI 근거에 해당 ID가 없어야 함.
3. A 작업 도중 B로 이동 → 늦은 보고는 A에만 저장.
4. 동일 message 두 번 → run ID 동일, 사용자 원문 1건, 모델 재실행 없음.
5. 같은 request_id의 다른 prompt → 409, 기존 run 보존.
6. 작업 중 삭제 → 409, 완료 후 확인 삭제 → 소속 객체·고정만 제거.
7. 재시작 도중 작업 → interrupted, 과거 결과 보존, 자동 API 호출 없음.

보관·복제·사건 종료·교차 사건 검색·다중 사용자 권한·미열람 알림은 후속 기능이다.
