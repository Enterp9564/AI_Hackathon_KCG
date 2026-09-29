# 링크온 수동 동기화 구현계획

기준: ../specs/2026-09-28-linkone-manual-sync.md. 사용자의 구현 요청 범위에서 현재 로컬 소스에 작업한다. 원래 수정·미추적 파일을 보존한다.

1. 데이터 계약/시험: UUID 검증·선택 필드·상태 누락·명부 제외·데이터 해시·개인별 diff 테스트부터 작성하고 실패를 확인한다. linkone_data.py로 구현한다.
2. 영속 세션/작업: LinkOneSync(store,engine,source)의 connect/sync/view/details/close. 가짜 외부 source와 실제 SQLite·Engine으로 최초 수신·반복·정정·실패·삭제 보호·재시작 시험. objects에 snapshot, session.linkone에 최소 현재 요약을 저장한다.
3. 읽기 전용 source: 격리 Python 및 고정 서버 키 검증 SSH 터널, parameterized SQL, 페이지 상한·시간 제한·조회 간격. 끝나면 자체 터널만 종료한다.
4. API/모델 연결: 목록·연결·세션별 동기화/상세/분석. 로컬 토큰 정책 재사용. 기존 실행 엔진은 source snapshot을 근거로 읽고 자동 사실 변경을 차단한다.
5. UI: 기존 스타일 안의 동기화 진입·상황 선택·진행/출처·명부/차이 상세·재수신/분석. 상태 갱신 중 다른 세션에 응답이 섞이지 않도록 한다.
6. 검증/문서: 전체 unittest, JS 구문, HTTP, 격리 브라우저와 실제 DB 조회. 13/PROGRESS/README/관련 요구 문서에 정확한 결과와 남은 한계를 기록한다.

주의할 실패: 동시에 두 번 연결해 중복 세션 생성, partial snapshot을 완전한 삭제로 해석, UI polling이 자동 외부 조회/AI 실행, 늦게 온 다른 사건 응답 혼입, 변경 없는 수신의 재분석, 과거 원본의 LLM 수정, 빈 명부를 0명 확정으로 표시.
