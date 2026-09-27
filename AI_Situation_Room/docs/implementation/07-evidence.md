# 07. 첨부·CSV·근거 검색

> 현재 구현 기준: 2026-09-27. [목록](README.md) · Store.add_attachment, [tools.py](../../prototype/tools.py)

## 1. 첨부 입력

브라우저에서 CSV/TXT/MD 한 파일을 선택한다. file.text()로 읽고 `{name,content}` JSON을 POST attachments로 전송한다. 업로드가 끝나면 자료 목록을 갱신하고 사용자가 별도 검토 요청을 보낸다. 업로드 자체는 모델을 호출하지 않는다.

- 확장자는 소문자 변환 후 `.csv`, `.txt`, `.md`만 허용한다.
- 파일명: 비어 있지 않은 문자열, 최대 120자. 저장명은 Path(name).name으로 경로를 제거한다.
- 본문: 비어 있지 않은 문자열, 최대 100,000자. 앞뒤 공백은 제거하여 저장한다.
- UI 제한은 `file.size ≤ 100,000 bytes`, 서버 본문 제한은 100,000문자다. 한글에서는 두 한도가 같지 않다.
- 전체 HTTP JSON 본문은 220,000바이트 이하. 다국어 JSON은 이 한도에도 걸릴 수 있다.
- PDF/Word/이미지 OCR·파일 삭제·자료 버전 관리는 없다.

## 2. CSV 계약

```csv
id,rescued
training-01,true
training-02,false
```

UTF-8 CSV를 사용한다. 서버는 선두 BOM을 제거하고 DictReader로 전체 행을 파싱한다. 데이터 행 1~10,000개, id/rescued 열이 필요하다. 추가 열은 허용되나 현재 집계에 사용하지 않는다.

id는 각 행에서 trim 후 비어 있지 않아야 하고 중복을 거절한다. rescued는 trim·소문자화 후 true/false/1/0만 허용한다. summary.total은 행 수, summary.rescued는 true 또는 1의 수다. 검색 상위 일부 행으로 총원을 계산하지 않는다.

CSV summary가 session.facts.total과 다르면 UI 확인 배너에 불일치를 표시한다. CSV 업로드만으로 총원이나 현재 명부를 바꾸지 않는다. 이 자료가 실제 탑승 명부인지 사용자가 확인해야 한다.

## 3. 근거 객체

기본 구조는 `{id,title,content}`이며 필요 시 summary/reported_at을 추가한다. 다음 순서로 evidence를 만든다.

1. basic_manual: 모든 세션에 공통 매뉴얼 본문.
2. donghae_assets: 공통 세력 JSON 전체와 출처 summary.
3. facts: 비어 있지 않을 때 현재 facts JSON과 버전 제목.
4. weather: 값이 있을 때 12의 조회 결과 JSON.
5. 사용자 신고 원문: message ID를 근거 ID로 사용, simulation 제외, reported_at 보존.
6. incident: 존재하면 현재 세부 장부 JSON.
7. 선택한 첨부 최대 5개: attachment ID, 파일명, 본문 앞 16,000자, summary.

공용 근거 ID는 세션 간 같은 이름을 쓸 수 있다. 사용자 근거 ID는 소속 세션의 snapshot에서만 얻는다. plan·전문요원 단계에서 원문 범위를 더 줄이는 규칙은 [03](03-sessions-memory.md)을 따른다.

## 4. 현재 단어 검색 알고리즘

query를 소문자화하고 정규식 `[\w가-힣]{2,}`로 2자 이상의 단어 집합을 얻는다. 첨부 본문을 소문자화한 뒤 각 단어가 부분 문자열로 포함되는 횟수(단어별 0/1)를 더해 score를 만든다.

CSV처럼 summary가 비어 있지 않으면 점수 0도 후보에 넣는다. 일반 문서는 score>0일 때만 후보에 넣는다. score 내림차순으로 정렬해 앞 5개를 사용한다. 동일 점수는 기존 첨부 순서를 따른다. CSV가 항상 5개 안에 보장되는 것은 아니다.

형태소 분석·임베딩·벡터DB·페이지 구절 검색·재순위화는 없다. 단어 검색으로 선택한 실제 본문을 모델 입력에 넣는 구조다. 역할별로 서로 다른 첨부를 정교하게 고르는 기능도 없다.

## 5. 출처와 화면

최종·개별 보고는 evidence_ids로 근거를 참조한다. UI는 기본 근거 ID를 설명명으로, message ID를 원문으로, attachment ID를 파일명으로 연결한다. 서버는 제공하지 않은 ID를 인용하면 보고를 거절한다. 인용된 ID가 있다고 주장 전체가 입증되는 것은 아니다.

자료 내용은 업무 입력이다. 첨부 안의 “이전 규칙을 무시하라” 같은 지시를 시스템 역할로 적용하지 않도록 모델 지침을 유지한다. 화면에서 자료·모델 출력을 HTML escape한다.

## 6. 수용 기준

- 중복/빈 id, rescued=unknown, 빈 CSV, 필수 열 누락 거절.
- BOM·대소문자 rescued 입력 정상 처리.
- A의 첨부를 B의 근거에 넣지 않음.
- 관련 TXT는 선택되고 무관한 TXT는 빠짐. 최대 5개·본문 16,000자 제한 확인.
- simulation 원문을 현장 사실 근거로 넣지 않음.
- CSV 불일치 표시 후에도 기존 facts 유지.
- 자료 업로드·자료 조회·화면 폴링만으로 calls가 늘지 않음.

벡터 검색을 추가한다면 세션 소속·공용 범위·문서 버전·구절 출처를 검색 단계에서 제한하고 현재 단어 검색과 비교 검증한다. 현재 완료 범위에 포함하지 않는다.
