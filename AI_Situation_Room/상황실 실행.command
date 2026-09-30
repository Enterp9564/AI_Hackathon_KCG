#!/bin/zsh
# Finder에서 더블클릭하여 실행합니다. API 키는 출력하지 않습니다.
cd -- "${0:A:h}" || exit 1
export PATH="/Library/Frameworks/Python.framework/Versions/3.11/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

rag_python="prototype/runtime/manual-rag/venv/bin/python"
rag_index="prototype/runtime/manual-rag/indexes/curated-main-v1"
if [[ ! -x "$rag_python" || ! -f "$rag_index/manifest.json" ]]; then
    print '벡터 검색 실행 환경이 준비되지 않았습니다. prototype/README.md의 국제 SAR 검색 준비 절차를 확인해주세요.'
    read -k 1 '?아무 키나 누르면 종료합니다.'
    exit 1
fi

"$rag_python" - <<'PYTHON'
import os
import json
import runpy
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

URL = 'http://127.0.0.1:8860/'

def ready():
    try:
        with urllib.request.urlopen(URL, timeout=1) as response:
            return 'AI 종합상황실' in response.read(10000).decode('utf-8')
    except Exception:
        return False

def open_browser():
    subprocess.run(['/usr/bin/open', URL], check=False)

if ready():
    with urllib.request.urlopen(URL+'api/config', timeout=2) as response:
        search = json.load(response).get('manual_search', {})
    if not search.get('available', search.get('mode') == 'hybrid' and search.get('ready_vector')):
        print('기존 서버의 벡터 검색이 비활성입니다. 기존 서버를 Control+C로 종료한 뒤 다시 실행해주세요.')
        sys.exit(1)
    print('상황실이 실행 중입니다. 벡터 검색은 설정창에서 켜고 끌 수 있습니다. 브라우저를 엽니다.')
    open_browser()
    sys.exit(0)

try:
    import certifi
except ImportError:
    print('인증서 패키지가 필요합니다. 터미널에서 python3 -m pip install certifi 실행 후 다시 열어주세요.')
    sys.exit(1)

key_file = Path('prototype/.secrets/openai_api_key.txt')
try:
    key = key_file.read_text().strip()
except OSError:
    print('API 키 파일을 읽을 수 없습니다: prototype/.secrets/openai_api_key.txt')
    sys.exit(1)
if not key:
    print('API 키 파일이 비어 있습니다. 키를 입력하고 다시 실행해주세요.')
    sys.exit(1)

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['OPENAI_API_KEY'] = key
sys.argv = ['prototype.server', '--port', '8860', '--manual-search', 'hybrid',
            '--manual-index', 'prototype/runtime/manual-rag/indexes/curated-main-v1']

def wait_and_open():
    for _ in range(40):
        if ready():
            open_browser()
            return
        time.sleep(0.25)

print('AI 종합상황실을 시작합니다. 잠시 후 브라우저가 열립니다.', flush=True)
print('사용 중에는 이 터미널을 열어두세요. 종료하려면 Control + C를 누르세요.', flush=True)
threading.Thread(target=wait_and_open, daemon=True).start()
try:
    runpy.run_module('prototype.server', run_name='__main__')
except OSError:
    print('서버를 시작하지 못했습니다. 8860 포트 사용 여부와 저장 폴더 권한을 확인해주세요.')
    sys.exit(1)
PYTHON

if (( $? != 0 )); then
    print '\n실행하지 못했습니다. 위 안내를 확인해주세요.'
    read -k 1 '?아무 키나 누르면 종료합니다.'
fi
