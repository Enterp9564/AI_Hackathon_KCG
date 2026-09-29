# 공개 국제 SAR 기반 초안

> 2026-09-28 · 원본 6개 / 561 PDF 페이지 / 한국어 초안 8개 / 선별 구절 14개. 앱 자동 연결·검색 성능·로컬 LLM 검증은 미실시.

## 분야별 문서

1. [조난 접수·신고 평가·기록](topics/01-intake.md)
2. [지휘·조정·기관 인계](topics/02-coordination.md)
3. [실종·표류·수색 계획](topics/03-search-planning.md)
4. [구조·인양·자원 선택](topics/04-rescue-resources.md)
5. [화재·침수·좌초·예인 지원](topics/05-vessel-emergency.md)
6. [다수 인명·명부·이송 조정](topics/06-mass-rescue.md)
7. [환자·환경 노출·의료정보 인계](topics/07-medical.md)
8. [상황 재검토·종결·재개](topics/08-review-close.md)

각 문서는 확인할 정보 → 근거 요약 → 적용 제한 → 우선 질문 → 보고 형식으로 구성했다. 확인 항목·질문·보고 형식은 HAEON의 작성 제안이다. 원문에 없는 문구를 국제 규정처럼 인용하지 않는다.

## 원본과 판본

- [AMSA National Search and Rescue Manual](originals/amsa-natsar-2026.pdf): 2026 Edition Version 1, February 2026, 519쪽. 소개에서 IAMSAR를 고려하여 작성했다고 설명한다. 호주 국가 매뉴얼이며 IAMSAR 원문 자체는 아니다. [공식 배포 페이지](https://www.amsa.gov.au/national-search-and-rescue-council/manuals-and-publications/national-search-and-rescue-manual).
- [MSC/Circ.959](originals/imo-msc-959.pdf): 2000-06-20, 조난 접수, 5쪽.
- [MSC.1/Circ.1183](originals/imo-msc-1183.pdf): 2006-05-31, 사고 억제를 위한 외부 지원, 6쪽.
- [MSC.1/Circ.1447](originals/imo-msc-1447.pdf): 2012-12-14, 수중 인명 인양 계획, 4쪽.
- [COMSAR/Circ.31](originals/imo-comsar-31.pdf): 2003-02-06, 대량구조, 21쪽.
- [MSC.1/Circ.1218](originals/imo-msc-1218.pdf): 2006-12-15, 해상 의료정보 교환, 6쪽.

IMO 문서들은 [공식 SAR 관련 문서 목록](https://www.imo.org/en/ourwork/safety/pages/imo-documents-relevant-to-sar.aspx)에서 연결된 원본을 받았다. 수집일에 목록에 있음을 확인했으며 후속 개정·국내 적용 규정 전체를 검토한 것은 아니다. IAMSAR 2025판은 그 목록에서 구매 출판물로 안내된다. 이번에는 IAMSAR 유료 본문 전체를 확보하지 않았다.

## 로컬 파일의 역할

- `originals/*.pdf`: 다운로드한 원본. 내용·표·각주·저작권 고지를 유지한다.
- `*.pages.jsonl`: PDF 페이지 단위 추출 텍스트. `pdf_page`는 1부터 시작한다. 표·그림은 PDF와 함께 읽어야 하며 추출 텍스트만으로 계산표를 해석하지 않는다.
- [sources.json](sources.json): 발행기관, 문서번호, 날짜, URL, 원본 해시, 읽은 페이지, 적용 범위.
- [chunks.jsonl](chunks.jsonl): 한국어로 선별한 14개 구절. 각 구절의 한계도 함께 모델에 전달할 대상으로 준비했다.
- [evaluation-cases.json](evaluation-cases.json): 향후 검색·답변 평가용. 모두 `not_run`이다.
- [downloads.json](downloads.json): 성공 파일과 확보하지 못한 후보의 기록.

AMSA PDF의 표지·판권 다음부터 인쇄 쪽번호가 시작하므로 예를 들어 **PDF 122쪽은 인쇄 120쪽**이다. `pdf_pages`와 `locator`를 함께 보관한다. 원본 561쪽 전체를 전문가 검토한 것으로 표시하지 않는다. `sources.json`의 인용 대상 절·페이지를 대조했다.

## 모델에 전달할 때 지킬 조건

1. 구절 본문뿐 아니라 출처·판본·적용 제한·초안 상태를 같이 전달한다.
2. 호주 기관의 권한·연락처·항공 기준을 국내 해양사고 지시로 복사하지 않는다.
3. 로컬에 저장한 과거 원본은 현재 기상·자원 위치·가용성 자료가 아니다.
4. 원본에 표류·수색 계산 내용이 있어도 앱에 검증된 계산기가 생긴 것은 아니다.
5. 의료 수치·약물·생존곡선·잠수·인양 장비 조작은 이번 선별 초안의 적용 범위 밖이다.
6. RAG 근거가 검색됐다는 이유로 외부 보고 승인·사건 확인·중복 실행 방지를 우회하지 않는다.

## 출처·이용 고지

© AMSA 2026. 원본 PDF 2쪽은 SAR 목적의 전체·부분 복제 시 출처 표시, 비상업적 사용, 저작권 고지 보존 조건을 명시한다. 원본 PDF와 페이지 추출본에서 해당 고지를 보존했다. 한국어 초안은 HAEON이 요약·구성한 것으로 AMSA나 IMO의 승인 번역이 아니다.

IMO 원문은 공식 무료 배포본을 수정하지 않고 보관했다. 공개 열람 가능 여부와 재배포·상업적 이용 조건은 구별한다. 이번에는 로컬 연구·해커톤 초안을 준비했으며 GitHub나 외부 서비스에 새 자료를 업로드하지 않았다.
