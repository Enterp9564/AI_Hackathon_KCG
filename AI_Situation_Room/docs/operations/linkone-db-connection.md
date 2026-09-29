# 링크온 DB 연결·동기화 운영 절차

작성·코드 대조: **2026-09-29**. 해온 내부 운영 문서. 비밀번호·개인키는 포함하지 않는다.

## 1. 현재 상태와 기존 문서

SSH 공개키 등록과 실제 읽기 전용 DB 접속은 2026-09-28 성공 기록이 있다. 이후 사건별 수신·저장·변경 비교·AI 분석이 구현됐다. 초기 등록 대기/접속 실패 기록은 당시의 이력이며 현재 준비 상태로 해석하지 않는다.

- [초기 접속 준비·과거 검증 이력](../handoff/linkone-access/README.md)
- [공개키 등록 요청](../handoff/linkone-access/PUBLIC_KEY_REQUEST.md)
- [접속 성공 결과](../handoff/linkone-access/CONNECTION_RESULT.md)
- [퀸메리호 시험 수신 결과](../handoff/linkone-access/QUEENMARY_RECEIVE_RESULT.md)
- [DB 스키마와 실제 조회 범위 비교](../handoff/linkone-access/SCHEMA_ACCESS_COMPARISON.md)
- [앱 수신·변경 비교 구현](../implementation/linkone-manual-sync.md)
- [데이터 의미·코드 해석](../../prototype/knowledge/linkone-semantics.md)

**이번 확인:** 기존 전용 Python 환경으로 `linkone_access.py local` 통과. 개인키/공개키 일치, 비밀 파일 권한·존재, 저장된 서버 지문, DB 드라이버 3.3.6을 확인했다. 서버에 새로 연결한 검사가 아니므로 현재 원격 서버 가용성·비밀번호 유효성까지 확인한 결과는 아니다. 앱·DB·자격증명 변경 없이 문서만 정리했다.

## 2. 연결 구조

링크온 → 해온의 단방향 읽기 연동이다. 현재 앱의 DB 수신은 MCP를 거치지 않는다. MCP 수신함은 별도 기능이다.

```mermaid
flowchart LR
    U[해온 담당자: 상황 선택 / 수동 동기화] --> H[해온 서버]
    H --> S[전용 Python 수신 프로세스]
    S --> T[SSH 공개키 인증 · 서버 호스트키 검증]
    T --> V[링크온 VM: 127.0.0.1:5432]
    V --> R[PostgreSQL linkone · linkone_ro]
    R --> P[선택 11개 표 · 사건별 읽기 전용 스냅샷]
    P --> L[해온 SQLite: 수신본 보존 · 변경 비교]
    L --> A[새 자료이면 분석 접수]
```

SSH는 DB까지의 암호화된 통로다. SSH 인증과 DB 인증은 별개이며 둘 다 준비해야 한다. 링크온 웹 화면 로그인 계정은 이 경로에서 사용하지 않는다.

## 3. 담당자 간 합의된 접속 정보

- SSH 서버: `114.110.181.118`, 도메인 `114-110-181-118.sslip.io`
- SSH 포트: **10022**
- SSH 계정: **linkone-link**
- 인증: 등록된 ED25519 공개키에 대응하는 개인키
- 권한: 원격 셸/명령 실행 불가. `127.0.0.1:5432`로 포트 포워딩만 허용
- 서버 ED25519 지문: `SHA256:RbdRpHgQVia1Ic9ZNRS0qLY9skVG24sCRkwYQse8QZ4`
- 등록된 해온 공개키 지문: `SHA256:x1bpt7FggGZXqU7AeKYOPimh/6P5ZFofQaiWTp8ys5Y`
- DB 종류: PostgreSQL. 상대 회신 버전은 16.15 / Ubuntu 24.04이며 이번에 재조회하지 않았다.
- VM 내부 DB 주소: `127.0.0.1:5432`
- DB 이름·스키마·계정: **linkone / public / linkone_ro**
- DB 비밀번호: 별도 비공개 파일. 이 문서에 기재하지 않음
- 네트워크: 상대 회신 당시 VPN·접속 IP 허용 등록 불필요. 환경 변경 시 담당자에게 재확인
- DB TLS: 현재 코드 `sslmode=disable`. SSH 터널이 암호화한다. 상대 설명의 자체 서명 인증서에 대한 `verify-full` 구성은 제공되지 않았다.
- 계정 종료: 상대 회신 당시 만료 없음. 프로젝트 종료 시점·키 폐기는 별도 협의

서버 지문은 **서버 신원 확인**, 공개키 지문은 **해온 클라이언트 키 확인**에 사용한다. 둘을 서로 비교하지 않는다. 서버 지문 변경 시 담당자의 확인을 받기 전 기존 고정값을 바꾸지 않는다.

## 4. 필요한 준비와 파일

### 링크온 담당자가 준비할 것

1. SSH 전용 계정에 해온 공개키를 등록하고 등록 지문을 대조해 회신한다.
2. SSH 10022 접근과 내부 DB 포워딩을 허용한다.
3. DB 읽기 계정·비밀번호·DB 이름·허용 범위·종료 일정을 전달한다.
4. 조회할 사건 `room.id`, 스키마 설명, 상태 코드와 이력 정정 규칙을 제공한다.
5. 접속 장애·키 변경·스키마 변경 시 연락할 담당자와 기존 연락 채널을 확정한다. 기존 전달 문서의 담당자 예시 문구는 실제 연락처 확정으로 간주하지 않는다.

### 해온 실행 PC에서 필요한 것

현재 구현은 macOS/Unix 경로를 전제로 한다. Python 3.11+, `/usr/bin/ssh`, `/usr/bin/ssh-keygen`, `/usr/bin/curl`, 전용 가상환경이 필요하다. DB 연결만을 위해 Node나 psql을 설치할 필요는 없다. Windows 그대로 실행은 검증하지 않았으며 고정 실행 경로·가상환경 경로 등의 대응이 필요하다.

- 개인키: `~/.ssh/haeon_linkone_ed25519` — 권한 600
- 공개키: `~/.ssh/haeon_linkone_ed25519.pub`
- DB 비밀번호: `prototype/.secrets/linkone/db_password` — 권한 600, 비어 있지 않은 값
- 서버 공개 호스트키: `prototype/.secrets/linkone/known_hosts` — 권한 600
- 수동 점검용 SSH 설정: `prototype/.secrets/linkone/ssh_config` — 권한 600
- DB Python 환경: `prototype/.secrets/linkone/venv`
- 패키지 고정 목록: [requirements.txt](../handoff/linkone-access/requirements.txt)
- 해온 저장: `prototype/runtime/room.sqlite` 및 실행 중 SQLite 관련 파일
- LIVE 분석 키: `prototype/.secrets/openai_api_key.txt` — DB 인증과 무관. 앱 실행 안내대로 환경변수에 로드

개인키·DB 비밀번호·known_hosts·ssh_config는 현재 코드가 심볼릭 링크를 거절하며 그룹/다른 사용자 권한이 없어야 한다. 비밀 파일을 문서·Git·전달 ZIP·브라우저 정적 폴더에 넣지 않는다. 기존 runtime과 비밀 파일을 초기화 목적으로 삭제하지 않는다.

## 5. 새 PC에서 최초 준비

기존 PC에는 이미 구성되어 있다. **기존 파일을 덮어쓰지 말고 없는 항목만 준비한다.** 아래 설정 예시는 macOS용이며 프로젝트 루트에서 실행한다.

### 5.1 키 생성과 공개키 등록

먼저 같은 이름의 키가 있는지 확인한다. 이미 등록된 키가 있으면 재사용한다. 새 PC용 키를 새로 만들 때만 다음을 실행한다.

```sh
ssh-keygen -t ed25519 -f ~/.ssh/haeon_linkone_ed25519 -C haeon-linkone-dev
ssh-keygen -lf ~/.ssh/haeon_linkone_ed25519.pub -E sha256
cat ~/.ssh/haeon_linkone_ed25519.pub
```

담당자에게 **공개키 한 줄과 그 SHA256 지문**만 전달하고 등록 완료 회신을 받는다. 개인키는 보내지 않는다. 새로 만든 키의 지문은 기존 등록 지문과 달라지므로 재등록이 필요하다.

현재 자동 수신은 `BatchMode=yes`이며 `local` 점검은 빈 키 암호로 공개키를 도출한다. 현재 구성은 암호 없는 개발 전용 키와 파일 권한 보호를 사용한다. 암호 있는 키를 쓰려면 키 잠금 해제/에이전트 정책 및 local 점검 방식을 먼저 보완해야 하며 현재 절차 그대로 작동한다고 가정하지 않는다.

### 5.2 전용 환경 설치

```sh
mkdir -p prototype/.secrets/linkone
chmod 700 prototype/.secrets/linkone
python3 -m venv prototype/.secrets/linkone/venv
prototype/.secrets/linkone/venv/bin/python -m pip install -r docs/handoff/linkone-access/requirements.txt
```

기존 가상환경이 있으면 재생성하지 않고 `local` 검사부터 한다. 현재 고정 목록은 psycopg 3.3.6, psycopg-binary 3.3.6, typing_extensions 4.16.0이다.

### 5.3 DB 비밀번호 저장

담당자에게 별도로 받은 비밀번호를 아래 숨김 입력으로 저장할 수 있다. 명령 인자·소스·터미널 출력에 값을 넣지 않는다. 기존 파일이 있으면 이 예시는 덮어쓰지 않고 실패한다. 비밀번호 교체는 기존 파일과 연결 영향 확인 후 별도 수행한다.

```sh
python3 - <<'PY'
import getpass, os
from pathlib import Path
path = Path('prototype/.secrets/linkone/db_password')
value = getpass.getpass('링크온 DB 비밀번호: ').strip()
if not value:
    raise SystemExit('빈 비밀번호는 저장하지 않습니다.')
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write(value + '\n')
print('비밀번호 파일 저장 완료. 값은 출력하지 않았습니다.')
PY
```

### 5.4 서버 호스트키 고정

담당자가 제공한 서버 공개 호스트키를 사용하거나 아래처럼 **임시 파일**에 수집한다. `ssh-keyscan` 수집 자체는 서버 신원 검증이 아니다.

```sh
ssh-keyscan -p 10022 -t ed25519 114.110.181.118 > /tmp/haeon-linkone-hostkey.candidate
ssh-keygen -lf /tmp/haeon-linkone-hostkey.candidate -E sha256
```

출력된 ED25519 지문을 3절의 **서버 지문**과 정확히 대조한다. 불일치·빈 결과·확인할 수 없는 복수 키가 있으면 중단한다. 일치한 `[114.110.181.118]:10022 ssh-ed25519 …` 행을 `prototype/.secrets/linkone/known_hosts`에 저장하고 권한 600을 적용한다. 기존 파일이 있으면 먼저 `local` 검사로 확인하고 임의로 덮어쓰지 않는다. `StrictHostKeyChecking=no`, HTTPS `curl -k`로 우회하지 않는다.

### 5.5 수동 점검용 SSH 설정

`prototype/.secrets/linkone/ssh_config`에 다음 내용을 둔다. `/절대/프로젝트경로`는 실제 경로로 바꾼다. 현재 PC의 프로젝트 루트는 `/Users/enterp/KCG_AIhackathon`이다.

```sshconfig
Host linkone-haeon
    HostName 114.110.181.118
    Port 10022
    User linkone-link
    IdentityFile ~/.ssh/haeon_linkone_ed25519
    IdentitiesOnly yes
    BatchMode yes
    PreferredAuthentications publickey
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    StrictHostKeyChecking yes
    HostKeyAlgorithms ssh-ed25519
    UserKnownHostsFile /절대/프로젝트경로/prototype/.secrets/linkone/known_hosts
    GlobalKnownHostsFile /dev/null
    ForwardAgent no
    RequestTTY no
    ExitOnForwardFailure yes
    ConnectTimeout 10
    ServerAliveInterval 10
    ServerAliveCountMax 2
    LocalForward 127.0.0.1:15432 127.0.0.1:5432
```

```sh
chmod 600 ~/.ssh/haeon_linkone_ed25519
chmod 600 prototype/.secrets/linkone/db_password prototype/.secrets/linkone/known_hosts prototype/.secrets/linkone/ssh_config
```

새 PC에서 Git 제외 상태도 `git check-ignore`로 확인한다. 해당 파일이 추적되지 않도록 프로젝트의 기존 제외 규칙을 유지한다. 비밀번호/개인키 내용은 점검 로그로 출력하지 않는다.

## 6. 접속 점검 순서

### A. 로컬 준비 확인

```sh
prototype/.secrets/linkone/venv/bin/python prototype/linkone_access.py local
```

기대 결과: `local_ready: true`. 네트워크 성공을 의미하지 않는다.

### B. 변경 신호 API 1회 확인

```sh
prototype/.secrets/linkone/venv/bin/python prototype/linkone_access.py sync
```

인증 없이 HTTPS GET으로 `all`과 지정 훈련 사건의 번호를 확인한다. 이는 SSH/DB 인증 시험이 아니다. 최소 5초 간격을 두며 이 명령은 반복 폴링을 시작하지 않는다.

### C. 수동 점검용 터널 시작 — 터미널 1

```sh
prototype/.secrets/linkone/venv/bin/python prototype/linkone_access.py tunnel
```

성공 시 별도 출력 없이 대기할 수 있다. 원격 셸이 뜨지 않는 것이 정상이다. 이 터미널을 유지한다. 로컬 `127.0.0.1:15432`에서 VM 내부 DB로 연결된다.

### D. DB 접속·권한·샘플 확인 — 터미널 2

```sh
prototype/.secrets/linkone/venv/bin/python prototype/linkone_access.py db
```

DB명·계정·읽기 전용 트랜잭션, 제외 컬럼 4개, public 일반/파티션 표의 쓰기 권한 메타데이터를 점검한다. INSERT/UPDATE/DELETE를 시험 실행하지 않는다. 현재 도구는 훈련 사건 `4957a3fb-b012-4e9a-87e1-57b4301cf6b9`에 고정돼 있으며 room/person/person_state/person_event/transfer 각각 최대20행의 **샘플 건수만** 출력한다. 전체 인원수나 앱 전체 수신 성공과는 다르다. 훈련 사건이 삭제됐다면 담당자에게 대체 시험 사건을 확인하고 도구의 ROOM을 갱신해야 한다.

### E. 종료

터미널 1에서 Control+C로 자신이 연 터널을 닫는다. 앱 자동 수신에는 이 수동 터널을 계속 켜둘 필요가 없다.

DBeaver를 사용할 경우 이 수동 터널을 켠 상태에서 DB 호스트 `127.0.0.1`, 포트 `15432`, DB `linkone`, 사용자 `linkone_ro`로 접속할 수 있다. 이 경우 DBeaver 자체 SSH 기능을 중복 활성화하지 않는다. 별도 GUI 접속 시험은 이번에 하지 않았다.

## 7. 해온 앱에서 수신·분석

1. [앱 실행 안내](../../prototype/README.md)에 따라 `상황실 실행.command` 또는 환경변수를 준비한 `python3 -m prototype.server --port 8860`으로 실행한다.
2. `http://127.0.0.1:8860/`에서 **링크온 동기화**를 누르고 실제 사건 목록에서 선택한다. 사건 이름만으로 동일성을 추정하지 않고 `room.id`가 연결 기준이다.
3. 사건별 해온 전용 세션을 만들거나 기존 연결 세션을 재사용한다.
4. 자료 수신 완료 후 새/변경 자료이면 분석을 자동 접수한다. LIVE는 실제 모델, DEMO는 규칙 응답이다. API 키 없이 DB 수신 자체는 가능하지만 LIVE 성공을 의미하지 않는다.
5. **승선원 · 변경 내역**에서 수신본·직전 차이·수신 시각을 확인한다.
6. 같은 자료이면 중복 저장/분석을 생략한다. 지침만 바뀌었거나 다시 조언이 필요하면 **현재 자료 재분석**을 사용한다. 이 버튼은 DB를 새로 읽지 않는다.
7. 현장 최신 자료가 필요하면 **링크온 동기화**를 다시 누른다. AI 검토 또는 수신 중에는 완료를 기다린다.

앱은 작업마다 `127.0.0.1`의 **임시 포트**에 SSH 터널을 열고 종료 시 자신의 터널만 닫는다. 수동 점검의 고정 15432와 다르다. 앱은 `ssh_config`를 읽지 않고 코드의 SSH 설정과 개인키/known_hosts/DB 비밀번호를 사용한다. 수동 설정만 바꾸면 앱 접속 대상도 바뀐다고 생각하지 않는다.

## 8. 조회 범위·부하·저장 정책

상대 제공 범위는 public 표33개(당시 회신)지만 앱이 수신하는 표는 아래 **11개와 선택 컬럼**이다.

`room`, `person`, `person_state`, `person_event`, `transfer`, `transport_order`, `no_accept`, `hull_tilt`, `room_closure`, `roster_upload`, `closure_place`.

- 컬럼 계약: [linkone_data.py의 COLUMNS](../../prototype/linkone_data.py). `SELECT *`를 사용하지 않는다.
- 제외 비밀 컬럼: account.password_hash, device_credential.token_hash, auth_session.token_hash, band.secret. 이 네 표에서 `SELECT *` 거절은 상대가 설명한 정상 권한 동작이다.
- 앱은 이름·나이·성별·상태 등 필요한 선택 정보를 수신하며 연락처·미디어 본문/URL 등을 전부 수신하는 것은 아니다. 부상 표시 좌표는 제한된 이벤트 필드로 수신한다.
- 사건별 전체 선택 자료를 한 읽기 전용 `REPEATABLE READ` 트랜잭션에서 페이지별 최대1000행으로 읽는다. 표당 최대20,000행 및 약20MB 수신 한도에서 초과 시 중단한다. 일부만 완전한 자료로 저장하지 않는다.
- SQL 제한 시간15초, DB 연결 제한10초, 소스 자식 프로세스 제한240초다. 이것은 정상 소요시간 목표가 아니다.
- 표/페이지 사이5초 대기는 없다. 연속 소스 작업(상황 목록 포함) 사이5초 간격을 둔다. 앱의 수신 작업은 직렬이다.
- 상황 목록은 생성 시각 역순이며 ACTIVE만으로 필터하지 않는다. 1000행이 반환되면 목록 한도 오류로 처리한다.
- 자료는 로컬 SQLite에 수신본과 비교 이력으로 보존한다. 수신 실패 시 마지막 저장본을 유지한다. 프로젝트 디렉터리 전체를 일반 정적 파일 서버로 제공하면 비밀/원본이 노출될 수 있으므로 앱 서버를 사용한다.
- LIVE에서는 선택된 수신 정보가 분석 모델 API로 전달된다. DB 열람 권한과 별개로 시험 자료의 사용·전달 범위를 유지한다. 공개 배포물에 runtime·비밀 파일을 넣지 않는다.

## 9. 변경 신호와 향후 자동 수신의 구분

상대 API: `GET https://114-110-181-118.sslip.io/api/sync?rooms=<room.id>`; 쉼표 구분 최대20개 사건. `all`은 서버 전체, `rooms[id]`는 사건별 번호이며 `web`은 해온 분석에 사용하지 않는다.

번호는 문자열로 비교한다. 서버 재시작 시 접두부가 바뀌며 숫자 대소 비교를 하지 않는다. 일부 쓰기는 all만 바뀔 수 있고 시간 경과만으로 변하는 상태는 신호가 없을 수 있다.

**현재 구현:** 담당자가 수동 조회하면 선택 자료를 다시 읽고, 수신 전후 번호를 메타데이터로 보존한다. 번호가 같다는 이유로 DB 조회를 생략하거나 번호 변화로 자동 폴링하지 않는다. 전후 번호가 달라도 자동 재수신하지 않으며 수신 이후의 새 변경까지 담았다고 보장하지 않는다. 필요 시 다음 수동 동기화로 갱신한다. API 신호 조회 실패는 unavailable로 기록하고 DB 수신을 시도한다.

**향후 증분 수신 요구:** 이력 id와 커밋 순서 차이 때문에 id 증가분만 읽으면 누락될 수 있다. 상대의 최근30초 `server_at` 중첩 조회+id 중복 제거 권고는 향후 증분 구현 때 적용할 항목이다. 현재는 전체 스냅샷 재조회여서 해당 증분 알고리즘을 구현한 것으로 설명하지 않는다. person_state.updated_at, 수정 시각이 없는 person/transfer 재조회, 재시작 기준 상태 재수신도 자동화 설계에서 다뤄야 한다.

## 10. 장애 대응

- **local 실패:** 전용 Python 실행 여부, 드라이버, 파일 존재/권한/심볼릭 링크, 키 쌍, 저장된 호스트키를 확인한다. 이 실패를 원격 DB 장애로 단정하지 않는다.
- **Permission denied:** SSH 계정·등록 공개키 지문·개인키 경로를 담당자와 대조한다. DB 비밀번호를 바꿔 해결할 문제가 아니다.
- **호스트키 불일치:** 중단 후 서버 변경 여부와 새 지문을 별도 연락으로 확인한다. known_hosts 삭제나 검증 해제로 진행하지 않는다.
- **연결 시간초과/거절:** 10022 접근, VM/SSH 상태, 로컬 네트워크를 확인한다. 포워딩 오류는 전용 계정의 목적지 `127.0.0.1:5432` 허용 여부를 확인한다.
- **15432 사용 중:** 수동 터널/DB 도구 사용 여부를 확인한다. 다른 프로세스를 임의 종료하지 않는다. 앱은 임시 포트를 쓴다.
- **DB 인증 실패:** SSH 통로와 별개로 linkone_ro 비밀번호·계정 유효성을 확인한다. 비밀번호를 오류 보고에 붙이지 않는다.
- **훈련 사건 없음:** 점검 도구 고정 ROOM이 여전히 존재하는지 담당자에게 확인한다. 다른 사건으로 무작위 바꾸지 않는다.
- **앱 상황 목록/수신 실패:** local → 수동 터널 → db 순서로 분리 점검한다. 1000개 사건 목록/행수·크기/SQL 시간 한도, 스키마 변경도 확인한다. 마지막 저장 자료는 남는다.
- **데이터는 수신됐지만 조언 실패:** LIVE 키/모델 연결 또는 분석 접수 상태를 확인하고 현재 자료 재분석을 사용한다. DB 실패와 AI 실패를 구별한다.
- **허용되지 않은 쓰기 요청:** 해온 로컬 API의 세션 토큰/Origin 검증 메시지일 수 있다. 동일한 localhost 주소로 새로고침해 재시도한다. 링크온 DB 쓰기 권한을 추가하는 해결책이 아니다.
- **HTTPS 인증서 오류:** 시스템 시간·신뢰 저장소·프록시를 점검한다. 현재 변경 신호 조회는 시스템 curl을 사용한다. 인증서 검증을 해제하지 않는다.

담당자에게 전달할 장애 기록은 발생 시각, 실패 단계, 해온 버전/실행 모드, 오류 종류, 사건 ID(필요한 경우)와 공개 지문으로 한정한다. 비밀번호·개인키·승선원 본문은 붙이지 않는다.

## 11. 운영 인수·종료 체크리스트

- [ ] 담당자·연락 경로·조회 사건 및 종료일을 확인했다.
- [ ] 공개키 등록 회신과 클라이언트/서버 지문 대조가 끝났다.
- [ ] local → sync → tunnel → db 결과를 각각 기록했다.
- [ ] 해온에서 사건 선택·수신본·LIVE/DEMO 구분·변경 비교를 확인했다.
- [ ] 동일 자료 재분석과 새 DB 동기화의 차이를 운영자가 이해했다.
- [ ] 백업 시 앱/수신을 종료하고 runtime을 보호된 위치에 보존한다. 비밀 자료 전달은 별도 승인된 방식으로 한다.
- [ ] 종료 시 상대에게 전용 공개키 제거/DB 계정 종료를 요청하고, 로컬 키·비밀번호·보관 데이터의 폐기 일정을 합의한다. 승인 없이 기존 파일을 삭제하지 않는다.

체크박스는 후속 운영자의 수행 기록용이며, 이번 문서 작성으로 전부 검증됐다는 의미가 아니다.

## 12. 코드와 문서의 책임 경계

- [linkone_access.py](../../prototype/linkone_access.py): 로컬/변경 신호/수동 터널/DB 접속 점검
- [linkone_source.py](../../prototype/linkone_source.py): 앱 전용 SSH 터널·DB 전체 수신·제한 시간
- [linkone_data.py](../../prototype/linkone_data.py): 허용 컬럼·정합성·비교·AI 근거
- [linkone_sync.py](../../prototype/linkone_sync.py): 전용 세션·수신 상태·중복 방지·분석 접수
- [prototype/README.md](../../prototype/README.md): 앱 실행 및 API 키 설정

서버/계정/키 경로 변경은 현재 `linkone_access.py`, `linkone_source.py` 및 비공개 수동 설정을 함께 검토해야 한다. 범용 접속 설정 UI는 제공하지 않는다. 이 문서 작성 과정에서 앱 기능·비밀 파일·원격 DB는 변경하지 않았다.
