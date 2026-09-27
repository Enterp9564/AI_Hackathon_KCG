"""Create ignored local credentials without displaying token values."""
import argparse
import json
import os
from pathlib import Path
import secrets
from .inbox import PROJECTS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', default=str(Path(__file__).parent/'.secrets'/'mcp'))
    args = parser.parse_args()
    folder = Path(args.directory)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths = [folder/'clients.json', *(folder/(p+'.token') for p in PROJECTS)]
    if any(p.exists() for p in paths):
        parser.error('기존 인증 파일이 있습니다. 덮어쓰지 않습니다. 기존 파일을 사용하거나 새 디렉터리를 지정하세요.')
    tokens = {p:secrets.token_urlsafe(32) for p in PROJECTS}
    for path, value in [(paths[0],json.dumps(tokens)), *((folder/(p+'.token'), t) for p,t in tokens.items())]:
        with os.fdopen(os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600),'w') as stream:
            stream.write(value+'\n')
    print('MCP 인증 파일 생성 완료. 서버에는 clients.json, 각 프로젝트에는 해당 .token 파일만 전달하세요.')
    print('저장 위치: '+str(folder))


if __name__ == '__main__': main()
