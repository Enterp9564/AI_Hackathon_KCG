# AI Situation Room · AI 종합상황실

담당자의 신고·정정·질문을 세션별로 기록하고, 상황실장과 전문요원의 검토·근거·대응 제안을 보여주는 로컬 프로토타입입니다. Python HTTP·SQLite·HTML/CSS/JavaScript를 사용합니다.

## 문서 시작점

- [문서 안내와 최신 결정](00_문서안내_최신결정.md)
- [현재 상태와 인수인계](13_현재상태_요구사항_인수인계.md)
- [기능별 상세 구현 문서](docs/implementation/README.md)
- [향후 프로젝트 API 연동](docs/improvements/01-project-api-integration.md)
- [개발 진입 지침](AGENTS.md)

## 실행

저장소 최상위에서 프로젝트 폴더로 이동합니다.

```sh
cd AI_Situation_Room
python3 -m prototype.server --port 8860
```

키 없이 직접 실행하면 DEMO를 사용할 수 있습니다. 브라우저에서 http://127.0.0.1:8860/ 을 엽니다. LIVE 설정·macOS 더블클릭·인증서는 [실행 README](prototype/README.md)를 따릅니다. 키와 runtime 데이터는 저장소에 포함하지 않습니다.

## 프로젝트 구성

- `prototype/`: 실제 앱, 테스트, 공통 매뉴얼, 가상 시나리오.
- `docs/`: 기능별 구현 명세, 개선안, 학습자료와 과거 개발계획.
- `presentation/`: 발표 HTML·원본 근거·미리보기. 실제 앱과 별도 산출물입니다.
- 루트의 번호 문서: 제품 요구·계획·설계·검증 이력.

검증 명령과 실제 결과는 [진행 기록](prototype/PROGRESS.md)을 확인합니다. 과거 문서 ZIP은 보존 자료이며 최신 문서를 자동 포함하지 않습니다.

## 외부 프로젝트 MCP 수신

Link-One·RESAID AI 보고는 수신함에 저장하며 담당자가 **인용하여 전송**한 경우에만 AI가 검토합니다. [MCP 계약](docs/implementation/17-mcp-transport.md) · [핫스팟 테스트 준비](docs/implementation/18-hotspot-testing.md). 실제 팀 앱·핫스팟 장비 검증은 아직 하지 않았습니다.
