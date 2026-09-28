# 12. 수동 기상 조회

> 임시 프로젝트명: **HAEON(해온)** · 해양경찰 멀티에이전트 의사결정 지원 시스템. [명칭·소개 기준](../PROJECT_NAMING.md) (2026-09-27). ‘AI 오케스트라’는 협업 방식의 설명이며 이름에 포함하지 않는다.

> 현재 코드의 계약이다. 외부 서비스 최신 명세·실응답 성공을 재검증한 기록은 아니다. [목록](README.md)

## 1. 입력과 실행 조건

담당자가 현재 상황 수정에서 위도·경도를 저장한 뒤 ‘조회 ↻’를 누른다. POST `/api/sessions/{sid}/weather`의 본문은 `{}`다. 서버가 세션 facts에서 lat/lon을 읽으며 브라우저 임의 좌표 본문을 사용하지 않는다.

좌표가 없으면 HTTP 400과 위치 입력 안내를 반환한다. 좌표는 facts 저장 때 위도 ±90·경도 ±180, 유한한 숫자로 검사한다.

## 2. 외부 요청

현재 [tools.weather](../../prototype/tools.py)는 HTTPS GET `https://api.open-meteo.com/v1/forecast`에 다음 쿼리를 보낸다.

```text
latitude=<facts.lat>
longitude=<facts.lon>
current=temperature_2m,wind_speed_10m,wind_direction_10m
wind_speed_unit=ms
timezone=Asia/Seoul
```

네트워크 timeout은 15초. 브라우저 weather fetch timeout은 22초다. 파고를 요청하지 않는다. 모델이 능동적으로 이 함수를 선택·호출하는 구조나 정기 스케줄러는 없다.

## 3. 저장 결과

```json
{
  "source":"Open-Meteo Forecast",
  "source_url":"https://api.open-meteo.com/v1/forecast?요청조건",
  "type":"모델 기반 자료 · 현장 실측 아님",
  "requested":{"lat":37.5,"lon":129.5},
  "returned":{"lat":37.5,"lon":129.5},
  "valid_at":"2026-09-27T12:00",
  "retrieved_at":1790478000.0,
  "timezone":"Asia/Seoul",
  "values":{"time":"2026-09-27T12:00","temperature_2m":20,"wind_speed_10m":4,"wind_direction_10m":90},
  "units":{"temperature_2m":"°C","wind_speed_10m":"m/s","wind_direction_10m":"°"},
  "marine":"해상 파고 미연동"
}
```

위 값은 형식 설명용 가상 예제다. returned 좌표는 공급자가 반환한 값이며 요청 좌표와 다를 수 있다. values와 units는 실제 payload의 current/current_units를 보존한다. 서버는 current와 current.time 존재를 검사하며 모든 기상 항목의 물리 범위를 별도로 검증하지는 않는다.

## 4. 버전·실패 처리

조회 전 session.version을 보관한다. 응답 후 Store.set_weather에서 현재 버전과 비교한다. 조회 중 상황이 바뀌었으면 409로 거절하고 오래된 결과를 저장하지 않는다. 성공하면 weather 저장·version+1·weather event를 남긴다. 기존 보고는 이전 버전으로 표시될 수 있다.

외부 요청 실패·자료 형식 실패 시 weather_failed 이벤트와 HTTP 502를 반환한다. 기존 기상은 유지하며 실제 조회가 성공한 것처럼 예시값으로 바꾸지 않는다.

LIVE 신고 patch의 lat/lon/location 변경은 기존 기상을 비운다. 수동 facts 교체에서는 lat/lon 변경 시 비우며 이전 weather를 이벤트에 보존한다. 두 경로의 무효화 조건 차이는 [04](04-incident-ledger.md)에 명시했다.

## 5. 화면과 근거

UI는 풍속·기온·단위·valid_at·timezone·조회시각·모델 기반 설명·파고 미연동을 표시한다. 모델 근거에는 weather ID로 전체 저장 객체를 제공한다. 수동 갱신을 ‘실시간 현장 실측’이라고 부르지 않는다.

유효시간 경과에 따른 자동 만료 기준은 없다. 화면이 1초마다 갱신되어도 기상 원본이 새로 조회되는 것은 아니다. 향후 만료 기준을 추가할 때는 관측시각·조회시각·좌표를 함께 비교한다.

## 6. 수용 기준

- 좌표 없음 → 400, 호출하지 않음.
- 정상 응답 mock → 출처·두 좌표·시각·단위 보존, 버전 증가.
- 네트워크 실패 → 502, 이전 자료 유지·실패 이벤트.
- 조회 중 사실 수정 → 409, 늦은 기상 덮어쓰기 없음.
- 좌표 변경 → 이전 위치 기상 제거.
- 반복 snapshot GET → weather 호출 횟수 증가 없음.
- 실제 응답 성공은 별도 네트워크 시험으로 기록. 해상 파고·자동 조회·MCP는 후속 범위.
