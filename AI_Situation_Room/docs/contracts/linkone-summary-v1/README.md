# 링크온 개발자용 상황 요약 JSON 예제

> **제안 계약·가상 데이터. 현재 아래 조회 API는 미구현이다.** 2026-09-28 사용자가 선택한 방식은 링크온이 필요할 때 조회하는 HTTP GET이다. 이번 예제 파일은 실제 현장 정보·LIVE 분석 결과가 아니다.

## 사용할 주소와 인자

`GET http://해온PC주소:8862/integration/v1/situation-summary?incident_id=7fa6f0ba-e99b-4e2b-8be4-36ec12d4a101`

링크온 서버에서 프로젝트 전용 Bearer 토큰으로 호출한다. 필수 query는 URL 인코딩한 `incident_id` 하나다. 해온에서 사건 연결과 **상황 요약 공유**를 켜야 조회할 수 있다. 토큰은 화면/브라우저 코드에 넣지 않는다.

사용자 제공 스키마에 맞춰 incident_id에는 **링크온 room.id(UUID)**를 쓰는 안을 제안한다. 아래 예제의 UUID는 가상 값이다. [DB 필드 대응·상태 해석](linkone-db-mapping.md)에서 room.case_no/room_session과의 구분, 구조·이송 집계, LIVE/DEMO와 REAL/DRILL의 차이를 확인한다.

일반 JSON 조회에는 MCP 초기화·JSON-RPC·MCP 버전 헤더가 필요 없다. 기존 `/mcp` 현장 보고 수신은 그대로 유지한다. 같은 포트에서 경로로 구분하는 설계다.

## 응답 예제

- [current.json](current.json): 현재 장부와 같은 버전의 분석. 인원 8명 중 구조 3명·미구조 5명. 외부 주장이 포함된 가상 분석.
- [stale.json](stale.json): 장부는 구조 4명·미구조 4명으로 변경됐지만, 요약은 이전 장부 기준. 새 분석은 진행 중.
- [unavailable.json](unavailable.json): 아직 분석 보고가 없고 현장 보고 1건은 수신함에서 대기 중.
- [field-report-v1.json](field-report-v1.json): 반대 방향으로 보내는 **현재 구현된** submit_field_report의 arguments 예제. 전체 JSON-RPC 본문이 아니다.

current/stale/unavailable 모두 정상 조회라면 HTTP 200이다. 오류는 `{"error":{"code":"incident_not_available","message":"조회 가능한 사건이 없습니다.","retryable":false}}` 형태의 JSON이며 인증/접근/서버 오류 HTTP 코드로 구분한다.

## 원하는 부분만 사용

- 요약 문장: `data["summary"]["text"]`
- 요약의 현재 장부 반영 여부: `data["summary"]["status"]`
- 현재 구조 인원: `data["situation"]["people"]["rescued"]`
- 현장 위치: `data["situation"]["location"]`
- 추가 확인 질문: `data["summary"]["information_requests"]`
- 새 분석 진행/실패: `data["processing"]["latest_analysis_status"]`
- 내용 변경 여부: `data["revision"]`의 같음/다름 비교

필드 누락에 대비해 선택적인 새 필드는 `.get()` 등으로 읽고 모르는 필드는 무시한다. 고정 v1 필드가 빠지거나 주 버전이 다르면 계약 오류로 처리한다. 미확인 숫자 `null`을 0으로 표시하지 않는다. `current`는 장부 버전 일치이며 모든 최신 신고/첨부 반영이나 현장 사실의 독립 검증을 보장하지 않는다.

## Python 서버 측 조회 예시 — 구현 후 사용

값을 출력하지 않는 예제다. HAEON_API_BASE와 LINKONE_API_TOKEN은 링크온 서버 환경에서 설정한다. 실제 값을 문서에 저장하지 않는다. HTTP는 실습망, HTTPS는 별도 TLS 구성이 있는 환경에서 사용한다.

```python
import http.client
import json
import os
from urllib.parse import urlencode, urlsplit

incident_id = "7fa6f0ba-e99b-4e2b-8be4-36ec12d4a101"
base = urlsplit(os.environ["HAEON_API_BASE"])
if base.scheme not in ("http", "https") or not base.hostname:
    raise ValueError("해온 API 주소 설정을 확인하세요.")
connection_type = (http.client.HTTPSConnection
                   if base.scheme == "https" else http.client.HTTPConnection)
connection = connection_type(base.hostname, base.port, timeout=5)
try:
    path = "/integration/v1/situation-summary?" + urlencode({"incident_id": incident_id})
    connection.request("GET", path, headers={
        "Authorization": "Bearer " + os.environ["LINKONE_API_TOKEN"],
        "Accept": "application/json",
    })
    response = connection.getresponse()
    if response.status != 200:
        raise RuntimeError(f"해온 조회 실패: HTTP {response.status}")
    data = json.load(response)
    if data["schema_version"].split(".")[0] != "1" or data["incident_id"] != incident_id:
        raise ValueError("응답 버전 또는 사건을 확인하세요.")
    summary_text = data["summary"]["text"]
    summary_status = data["summary"]["status"]
    rescued = data["situation"]["people"]["rescued"]
finally:
    connection.close()
```

이 예제는 redirect를 따라 토큰을 다른 주소로 보내지 않는다. 실제 화면에서는 stale/unavailable·연결 실패·DEMO를 표시한다. 요청은 겹치지 않게 하고 사건 전환 후 늦은 이전 응답은 버린다. 세부 timeout/재시도 규칙은 설계 §8을 따른다.

## 확장 원칙

현재 공통 인자를 유지하고 `extensions` 또는 새 선택 필드에 정보를 추가한다. v1.0의 extensions는 빈 객체다. 위치·기상·구조 진행 같은 세부 필드가 필요하면 이름·단위·출처·시각·확실성을 함께 합의한다. 필드 삭제/자료형/의미 변경은 v2 계약으로 나눈다.

링크온 → 해온의 현재 수신 5개 필드는 그대로다. 임의 새 필드를 붙이면 현재 서버는 거절한다. 구조화 현장 데이터 추가는 별도 v2 수신 계약에서 다룬다.

[전체 인자·상태·오류 설계](../../superpowers/specs/2026-09-28-linkone-summary-api.md) · [작업별 구현계획](../../superpowers/plans/2026-09-28-linkone-summary-api.md)
