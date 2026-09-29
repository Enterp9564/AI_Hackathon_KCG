# 해온 SSH 공개키 등록 요청

2026-09-28 · 링크온 개발 담당자 전달용

안녕하세요. 해온 개발용 SSH 공개키를 전달드립니다.
서버 `114.110.181.118:10022`의 터널 전용 계정 `linkone-link`에 아래 키를 등록해 주십시오.

## 공개키

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKDLYk0zT4dsH2AA6qO0asDP+YirQrLPF6yTP3r8z210 haeon-linkone-dev
```

## SHA256 지문

```text
256 SHA256:x1bpt7FggGZXqU7AeKYOPimh/6P5ZFofQaiWTp8ys5Y haeon-linkone-dev (ED25519)
```

첨부 `haeon_linkone_ed25519.pub`는 위 공개키와 같습니다. 개인키·DB 비밀번호는 포함하지 않았습니다.

등록 후 완료 회신을 부탁드립니다. 등록되면 서버 지문을 대조하고 SSH 터널로 읽기 전용 DB 접속을 확인하겠습니다.

변경 확인 5초·조회당 최대 1,000건·첫 시험 사건 `(훈련) 낚시어선 충돌` 기준을 확인했습니다. 연동 방향은 링크온 → 해온 읽기 전용입니다.
