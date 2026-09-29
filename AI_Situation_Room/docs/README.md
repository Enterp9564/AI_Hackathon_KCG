# HAEON(해온) 문서 시작점

> 2026-09-29: [국제 SAR 검색 M1 상세](implementation/24-local-manual-rag.md) 구현. 기본 off인 시험 기능이며 [검증 기록](superpowers/plans/2026-09-29-sar-rag-progress.md)에 완료 범위·남은 제한을 구분했다. 아래 2026-09-28 계획/자료 준비 기록 이후의 변경이다.

해양경찰 멀티에이전트 의사결정 지원 시스템의 문서 안내다. 임시 이름은 HAEON(해온)이며 AI 오케스트라는 협업 방식의 설명이다.

- **다른 AI 플랫폼에 전달:** [재구현 전달 안내](handoff/README.md). 통합 명세 하나에 계약·순서·화면·예제·매뉴얼·가상 시나리오를 포함한다.
- **기존 앱을 수정:** [현재 상태와 인수인계](../13_현재상태_요구사항_인수인계.md) → [기능별 상세 명세](implementation/README.md).
- **링크온 DB 연결·운영:** [준비·접속·동기화·장애 대응 통합 절차](operations/linkone-db-connection.md). 수동 점검용 터널과 앱 자동 터널을 구분한다.
- **개발 순서:** [재구현 실행 계획](handoff/REBUILD_PLAN.md). 현재 복원과 미구현 개선을 분리한다.
- **폴더를 정리/확장:** [폴더 구조 검토](FOLDER_GUIDE.md).
- **이름·소개:** [명칭 기준](PROJECT_NAMING.md).
- **향후 연동:** [프로젝트 API 개선 방향](improvements/01-project-api-integration.md).
- **주요 알림 개선안:** [고정 요약·여러 환자 비교·클릭 전 버튼 강조](improvements/04-main-alerts.md). 화면·데이터 처리·구현 순서를 나눈 제안이며 아직 앱에 적용하지 않았다.
- **링크온 상황 요약 조회:** [통신 인자·설계](superpowers/specs/2026-09-28-linkone-summary-api.md) · [구현계획](superpowers/plans/2026-09-28-linkone-summary-api.md) · [JSON 예제](contracts/linkone-summary-v1/README.md). 링크온이 필요할 때 조회하는 방식이며 신규 API는 미구현이다.
- **교육 준비:** [1·2일차 예습자료](prestudy/README.md).

implementation은 편집 원본, handoff의 통합 명세는 그 시점의 생성된 전달본이다. superpowers의 날짜별 계획, 발표 sources, 과거 ZIP은 역사 자료다. 이번 문서화로 새 기능이 구현되거나 LIVE 검증이 완료된 것은 아니다.

- [사고해점 기상 API 검토](improvements/02-incident-weather.md): 현장 보고 우선, 주변 관측·모델 예보 보완 방향. 미구현 개선사항.
- [구난구조 매뉴얼 로컬화](improvements/03-local-manuals.md): 공개 국제 SAR 원본·한국어 초안 준비와 후속 개선. 선별 요약 검색은 M1 구현, 로컬 생성 LLM은 미연결.
- [국제 SAR 검색·요원 연동 구현계획](superpowers/plans/2026-09-28-sar-rag.md): 2026-09-28 단계별 계획. M1 일부 구현·검증 범위는 최신 실행 기록을 우선한다.
