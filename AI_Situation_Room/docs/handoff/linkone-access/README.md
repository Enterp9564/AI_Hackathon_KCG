# 링크온 접속 준비 — 해온 내부 실행 안내

> **현행 운영 절차(2026-09-29): [DB 연결·동기화 운영 문서](../../operations/linkone-db-connection.md)**. 새 PC 준비, SSH 키 등록·호스트키 검증, 비밀번호 보관, 수동 점검과 앱 수신의 차이, 장애 대응을 통합했다. 아래 등록 대기·실패·성공 항목은 2026-09-28 당시의 순차 기록이며, 후반의 접속 성공과 앱 연동 구현 이후 상태를 우선한다.

## 상대방에게 전달할 파일

- [공개키 등록 요청](PUBLIC_KEY_REQUEST.md)
- [공개키 파일](haeon_linkone_ed25519.pub)

위 두 파일만 전달하면 됩니다. 이 내부 실행 안내와 `.secrets` 폴더는 전달 대상이 아닙니다. 사용자가 공개키 전달을 완료했다고 확인했습니다. 링크온 측 등록 완료 회신을 받았고 SSH·DB 읽기 접속까지 성공했습니다.

## 로컬 구성

- 개인키: `~/.ssh/haeon_linkone_ed25519` (권한 600, 암호 없는 개발 전용 키)
- DB 비밀번호: `prototype/.secrets/linkone/db_password` (권한 600)
- SSH 설정·검증한 서버 키: `prototype/.secrets/linkone/ssh_config`, `known_hosts`
- Python 환경: `prototype/.secrets/linkone/venv`
- DB 도구: `psycopg[binary]` 3.3.6. `psql`은 설치하지 않았으며 아래 Python 점검 도구로 조회합니다.
- 위 `.secrets` 경로는 기존 Git 제외 규칙의 적용을 받습니다. 개인키도 저장소 밖에 있습니다.

SSH는 지정 키만 사용하고, 서버 지문 검증을 강제합니다. 로컬 포트는 `127.0.0.1:15432`에만 열며 원격 셸·에이전트 전달·비밀번호 인증은 사용하지 않습니다. 기본 SSH 설정은 변경하지 않았습니다.

## 실행

프로젝트 루트 `/Users/enterp/KCG_AIhackathon`에서 실행합니다.

### 1. 로컬 준비 상태

```sh
prototype/.secrets/linkone/venv/bin/python prototype/linkone_access.py local
```

### 2. 변경 신호 1회 조회

```sh
prototype/.secrets/linkone/venv/bin/python prototype/linkone_access.py sync
```

시스템 curl의 HTTPS 인증서 검증을 사용합니다. 자동 폴링은 시작하지 않습니다. 반복 실행할 때는 최소 5초 간격을 둡니다.

### 3. 공개키 등록 회신 후 터널 시작

```sh
prototype/.secrets/linkone/venv/bin/python prototype/linkone_access.py tunnel
```

접속에 성공하면 출력 없이 대기할 수 있습니다. 이 터미널을 유지하고 다른 터미널에서 DB 점검을 실행합니다. 종료는 Control+C입니다. `Permission denied`이면 담당자의 공개키 등록 여부를 확인합니다. `Address already in use`이면 15432를 사용 중인 프로세스를 확인하며 임의 종료하지 않습니다. 호스트키 불일치 시 연결을 중단하고 담당자와 새 지문을 대조합니다.

### 4. DB 점검

```sh
prototype/.secrets/linkone/venv/bin/python prototype/linkone_access.py db
```

읽기 전용 트랜잭션에서 DB·계정·권한을 확인하고, 합의한 훈련 사건의 핵심 5개 테이블에서 각각 최대 20행을 조회합니다. 출력은 샘플 건수와 권한 판정뿐이며 개인정보 본문·비밀번호는 표시하거나 저장하지 않습니다. 건수는 전체 인원수가 아닙니다. INSERT/UPDATE/DELETE로 권한을 시험하지 않습니다.

이것은 수동 접속 점검 도구입니다. 자동 동기화, 30초 중복 조회, DB 전체 권한 감사, 해온 장부 자동 반영을 구현한 것으로 취급하지 않습니다.

## 초기 준비 단계 확인 결과 · 공개키 등록 전 이력

- 전용 키 생성·공개키/개인키 일치·로컬 비밀 파일 권한 검사: 통과
- SSH 서버 ED25519 지문: 담당자 제공 지문과 일치
- 변경 API: 시스템 curl로 정상 JSON 응답 확인
- Python 기본 HTTPS 시도: 인증서 연결 오류로 실패. 인증서 검증을 해제하지 않고 시스템 curl로 재확인 성공
- SSH 인증 시험: `Permission denied (publickey,password)`로 실패. 클라이언트는 공개키 인증만 시도했으며 키 등록이 필요함
- DB 인증·실데이터 조회: 공개키 등록 및 터널 개통 후 실시

비밀번호 저장 과정의 첫 시도는 표준입력이 비어 빈 파일이 생성됐습니다. 전달받은 값으로 바로잡았고 로컬 검사에서 비어 있지 않음과 권한을 확인했습니다. 비밀번호 값은 로그·문서에 기록하지 않았습니다.


## 검증 기록 · 2026-09-28

- `local` 명령 통과: 키 쌍 일치, 서버 지문, 비밀 파일 권한, 비밀번호 비어 있지 않음, 드라이버 3.3.6 확인
- `sync` 명령 통과: 전체 번호와 지정 훈련 사건 번호를 읽음. 서버 응답 본문에 사건 개인정보 없음
- Python 구문 검사 통과
- `python3 -m unittest prototype.tests.test_linkone_access -v`: 5개 통과. 모의 DB로 읽기 전용 접속 옵션, 제한 컬럼 노출/쓰기 권한 발견 시 중단, 본문/비밀번호 비출력, 파일 권한·심볼릭 링크 거절 확인
- `git check-ignore`로 비밀번호·SSH 설정·가상환경 제외 확인
- 실제 PostgreSQL 권한·SQL 실행 결과는 공개키 등록 후 검증 필요. 앱 전체 회귀/브라우저/LIVE 시험은 미실시

설치 버전은 `requirements.txt`에 기록했습니다. 환경을 다시 준비할 때는 전용 가상환경에서만 설치하십시오.


## 공개키 송신 후 개발 환경 재확인

사용자가 공개키 전달 완료를 알린 뒤 아래 검사를 다시 실행했다. 이전 SSH 인증 실패 기록은 보존한다.

- Python 3.11.9, SQLite 3.45.1, Node v24.7.0, SSH·Git·시스템 curl 확인
- 전용 가상환경 psycopg 3.3.6 및 pip 의존성 검사 통과. pip 캐시 쓰기 경고는 있었으나 의존성 충돌 없음
- local 점검 통과: 키 쌍·검증된 서버 지문·비밀 파일 권한·비밀번호 존재
- 접속 도구 모의 보호 시험 5개 재실행 통과
- 전달 ZIP의 공개키·전달용 공개키·로컬 공개키 일치 확인
- 비밀번호·SSH 설정·known_hosts·가상환경의 Git 제외 재확인
- 변경 API 재조회 성공: all=b4acf3a3.27, 훈련 사건=b4acf3a3.0. 전체 번호만 바뀐 사례이며 원인은 조회하지 않음
- SSH 인증 재시도: 종료 코드 255, Permission denied(publickey,password). 등록 미완료인지 서버 설정/등록키 문제인지는 이 결과만으로 확정할 수 없음
- 터널 개통·실제 PostgreSQL 인증/권한/데이터 조회는 미실시. 로컬 환경 준비와 원격 연결 성공을 구분함

다음 외부 확인은 링크온 담당자의 공개키 등록 완료 회신이다. 완료 회신 후에도 인증이 거절되면 등록 계정 linkone-link와 공개키 SHA256 지문 일치를 함께 확인한다. 이 점검에서 장기 실행 터널이나 자동 폴링 프로세스는 남기지 않았다.


## 공개키 등록 후 실제 접속 성공

링크온의 등록 완료 회신 후 SSH 터널 및 DB 점검을 실행했다. 서버 키 고정 검증을 통과했고 linkone/linkone_ro 읽기 전용 접속에 성공했다. 제외 컬럼 4개 조회 차단과 public 일반·파티션 테이블의 쓰기 권한 메타데이터를 확인했다. 실제 쓰기 명령은 실행하지 않았다.

첫 훈련 사건의 room은 1행이나 person/person_state/person_event/transfer는 0행이었다. 함께 제공된 퀸메리호 사건은 각 최대 20행 샘플 조회에서 person 20, person_state 6, person_event 20, transfer 0을 반환했다. 전체 인원수로 해석하지 않는다. 반환한 행 본문은 출력·저장하지 않았다.

[링크온에 전달할 접속 결과](CONNECTION_RESULT.md)를 작성했다. 이력 동기화·인원 집계·해온 장부 반영·AI 분석 연동과 이송 실데이터 검증은 아직 하지 않았다. 이전 인증 실패 기록은 당시 결과로 보존한다.

점검용 SSH 터널은 시험 후 종료했습니다. 자동 재접속·폴링은 실행하지 않습니다.


## 퀸메리호 시험 수신

[실제 수신 결과와 검증 범위](QUEENMARY_RECEIVE_RESULT.md)를 참고한다. 선택한 10개 테이블의 사건별 스냅샷을 로컬 runtime에 보관했으며 해온 장부에는 아직 반영하지 않았다.
