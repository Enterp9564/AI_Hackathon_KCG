# AI Hackathon KCG

여러 협업 프로젝트를 함께 관리하는 저장소입니다. 프로젝트별 코드는 최상위의 독립 폴더에 둡니다.

## Projects

- [AI Situation Room](AI_Situation_Room/README.md): AI 종합상황실 — 담당자 대화, 전문요원 검토, 사건 장부와 고정 상황판.

추가 협업 프로젝트 두 개는 이름이 정해지면 `AI_Situation_Room/`과 같은 깊이에 폴더를 추가하고 이 목록에 연결합니다. 각 프로젝트의 실행 방법·설정·자료는 해당 폴더에서 관리합니다.

프로젝트 간 API 정보 교환은 [AI 상황실의 향후 개선안](AI_Situation_Room/docs/improvements/01-project-api-integration.md)에 기록되어 있습니다. 실제 연결 대상·인증·데이터 계약은 아직 미정입니다.

## Repository conventions

- 각 프로젝트 폴더에서 작업하고 상대경로를 유지합니다.
- 비밀키·환경설정 원본·런타임 DB·캐시를 커밋하지 않습니다.
- 실제 실행 시험과 문서·발표 설명을 구별합니다.
