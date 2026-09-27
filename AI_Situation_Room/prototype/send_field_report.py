"""Deterministic test client. Reuse --report-id for safe retries."""
import argparse
import json
from pathlib import Path
import urllib.request
import urllib.error
from .mcp_server import PROTOCOL


def main():
    p = argparse.ArgumentParser(description='MCP 테스트 보고 제출 · 수신만으로 AI는 실행되지 않음')
    p.add_argument('--url', default='http://127.0.0.1:8862/mcp')
    p.add_argument('--token-file', required=True)
    p.add_argument('--incident-id', required=True)
    p.add_argument('--incident-title', required=True)
    p.add_argument('--report-id', required=True)
    p.add_argument('--reported-at', required=True)
    p.add_argument('--content', required=True)
    args = p.parse_args()
    token = Path(args.token_file).read_text().strip()
    # Do not follow redirects with the bearer credential.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw): return None
    opener = urllib.request.build_opener(NoRedirect)
    def call(method, params, rid=None):
        body = dict(jsonrpc='2.0', method=method, params=params)
        if rid is not None: body['id'] = rid
        request = urllib.request.Request(args.url, data=json.dumps(body,ensure_ascii=False).encode(),
            headers={'Authorization':'Bearer '+token, 'Content-Type':'application/json',
                     'Accept':'application/json, text/event-stream','MCP-Protocol-Version':PROTOCOL})
        with opener.open(request,timeout=15) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    try:
        initialized = call('initialize',dict(protocolVersion=PROTOCOL, capabilities={},clientInfo={'name':'team-test-sender','version':'1.0'}),1)
        if initialized.get('result',{}).get('protocolVersion') != PROTOCOL:
            raise ValueError('MCP 초기화 실패')
        call('notifications/initialized', {})
        print(json.dumps(call('tools/list',{},2),ensure_ascii=False,indent=2))
        report = {k:getattr(args,k) for k in ('report_id','incident_id','incident_title','reported_at','content')}
        result = call('tools/call',dict(name='submit_field_report',arguments=report),3)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if 'error' in result or result.get('result',{}).get('isError'): raise SystemExit(1)
    except (OSError, ValueError):
        p.exit(1, 'MCP 전송 실패. 주소·포트·인증 파일·사건 연결을 확인하세요. 재시도는 동일한 보고 ID와 내용을 사용하세요.\n')


if __name__ == '__main__': main()
