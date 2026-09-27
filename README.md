# AI Hackathon KCG

여러 협업 프로젝트를 함께 관리하는 저장소입니다. 프로젝트별 코드는 최상위의 독립 폴더에 둡니다.

## Projects

- [AI Situation Room](AI_Situation_Room/README.md) — 김대성·송민주: 담당자 대화, 전문요원 검토, 사건 장부와 고정 상황판.
- [Link-One](Link_One/README.md) — 신진섭: 현장 구조 정보와 구조 대상자의 위치·상태 관리. 프로젝트 업로드 준비 폴더.
- [RESAID AI](RESAID_AI/README.md) — 채민주: 대상자 상태에 따른 응급 지원과 확인사항. 프로젝트 업로드 준비 폴더.

세 프로젝트는 저장소 최상위의 독립 폴더에서 관리합니다. 각 팀원은 자신의 프로젝트 폴더에 코드와 자료를 추가하고 실행 방법을 해당 README에 기록합니다. 현재 Link-One과 RESAID AI에는 안내 문서만 있습니다.

프로젝트 간 API 정보 교환은 [AI 상황실의 향후 개선안](AI_Situation_Room/docs/improvements/01-project-api-integration.md)에 기록되어 있습니다. 실제 연결 대상·인증·데이터 계약은 아직 미정입니다.

## Repository conventions

- 각 프로젝트 폴더에서 작업하고 상대경로를 유지합니다.
- 비밀키·환경설정 원본·런타임 DB·캐시를 커밋하지 않습니다.
- 실제 실행 시험과 문서·발표 설명을 구별합니다.
