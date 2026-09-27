"""MCP 2025-11-25 Streamable HTTP: stateless JSON responses, one intake tool.

Lab authentication uses pre-shared per-project tokens, not OAuth discovery.
No chat, approval, session listing or fact-update tools are exposed here.
"""
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .inbox import FIELDS, PROJECTS

PROTOCOL = '2025-11-25'
TOOL = dict(name='submit_field_report', title='현장 보고 수신함에 제출',
    description='외부 보고를 수신함에 저장합니다. 담당자 승인 전에는 AI 실행이나 상황판 갱신을 하지 않습니다. 재시도는 같은 report_id와 동일한 원문을 사용하세요.',
    inputSchema={'type':'object', 'properties':{k:{'type':'string','minLength':1,'maxLength':v} for k,v in FIELDS.items()},
                 'required':list(FIELDS), 'additionalProperties':False},
    annotations={'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False})


def validate_tokens(tokens):
    if not isinstance(tokens, dict) or set(tokens) != set(PROJECTS):
        raise ValueError('두 프로젝트의 MCP 토큰 파일이 필요합니다.')
    if any(not isinstance(t,str) or not 32 <= len(t) <= 256 or not t.isascii() or any(c.isspace() for c in t) for t in tokens.values()):
        raise ValueError('MCP 토큰 형식이 잘못되었습니다. prepare_mcp로 생성하세요.')
    if len(set(tokens.values())) != len(tokens):
        raise ValueError('프로젝트별로 다른 토큰이 필요합니다.')
    return tokens


def load_tokens(path):
    return validate_tokens(json.loads(Path(path).read_text()))


def make_mcp_server(inbox, tokens, host='127.0.0.1', port=8862, allowed_hosts=()):
    tokens = validate_tokens(tokens)
    if host not in ('127.0.0.1','localhost') and not allowed_hosts:
        raise ValueError('LAN 수신에는 --mcp-allowed-host로 실제 상황실 IP를 지정하세요.')
    if any('/' in h or ':' in h or not h for h in allowed_hosts):
        raise ValueError('허용 호스트에는 포트 없는 IPv4 주소 또는 호스트명을 입력하세요.')

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass  # Authorization and report contents never enter access logs.

        def respond(self, status, data=None):
            body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode() if data is not None else b''
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            if status == 405: self.send_header('Allow','POST')
            if status == 401: self.send_header('WWW-Authenticate','Bearer realm="mcp-intake"')
            self.end_headers()
            self.wfile.write(body)

        def access(self):
            if self.path != '/mcp':
                self.respond(404, {'error':'MCP endpoint is /mcp'}); return None
            hosts = {f'{h}:{self.server.server_port}' for h in ('127.0.0.1','localhost',*allowed_hosts)}
            if self.headers.get('Host') not in hosts or (self.headers.get('Origin') and self.headers['Origin'] not in {'http://'+h for h in hosts}):
                self.respond(403, {'error':'Host or Origin not allowed'}); return None
            auth = self.headers.get('Authorization','')
            if not auth.isascii():
                self.respond(401, {'error':'Authentication required'}); return None
            for project, token in tokens.items():
                if secrets.compare_digest(auth, 'Bearer '+token): return project
            self.respond(401, {'error':'Authentication required'}); return None

        def do_GET(self):
            if self.access(): self.respond(405)

        do_DELETE = do_GET

        def do_POST(self):
            project = self.access()
            if not project: return
            rid = None
            try:
                if self.headers.get('Transfer-Encoding'):
                    return self.respond(400, {'error':'Content-Length required'})
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 40000: return self.respond(413, {'error':'Request limit: 40000 bytes'})
                if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                    return self.respond(415, {'error':'application/json required'})
                accept = self.headers.get('Accept','')
                if 'application/json' not in accept or 'text/event-stream' not in accept:
                    return self.respond(406, {'error':'Accept application/json and text/event-stream'})
                try: request = json.loads(self.rfile.read(length))
                except (ValueError, UnicodeError):
                    return self.respond(400, {'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Parse error'}})
                if not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or not isinstance(request.get('method'),str):
                    raise ValueError('Invalid JSON-RPC request')
                rid = request.get('id')
                if 'id' in request and (type(rid) not in (int,str)):
                    rid = None; raise ValueError('Invalid request id')
                method = request['method']
                version = self.headers.get('MCP-Protocol-Version')
                if (version and version != PROTOCOL) or (not version and method != 'initialize'):
                    return self.respond(400, {'error':'Supported MCP-Protocol-Version: '+PROTOCOL})
                params = request.get('params', {})
                if not isinstance(params, dict): raise ValueError('params must be an object')
                if 'id' not in request:
                    if not method.startswith('notifications/'):
                        raise ValueError('Requests require an id')
                    return self.respond(202)
                if method == 'initialize':
                    if not isinstance(params.get('protocolVersion'),str) or not isinstance(params.get('capabilities'),dict) or not isinstance(params.get('clientInfo'),dict):
                        raise ValueError('Invalid initialize parameters')
                    result = dict(protocolVersion=PROTOCOL, capabilities={'tools':{'listChanged':False}},
                                  serverInfo={'name':'ai-situation-room-intake','version':'1.0.0'},
                                  instructions='Reports are unverified. Human approval is required for AI review.')
                elif method == 'ping': result = {}
                elif method == 'tools/list': result = {'tools':[TOOL]}
                elif method == 'tools/call':
                    if params.get('name') != 'submit_field_report':
                        return self.respond(200, {'jsonrpc':'2.0','id':rid,'error':{'code':-32602,'message':'Unknown tool'}})
                    try:
                        report = inbox.receive(project, params.get('arguments'))
                        receipt = dict(receipt_id=report['id'], report_id=report['original']['report_id'],
                                       status=report['status'], received_at=report['received_at'], requires_human_approval=report['status'] in ('pending','deferred'))
                        result = {'content':[{'type':'text','text':json.dumps(receipt,ensure_ascii=False)}],
                                  'structuredContent':receipt,'isError':False}
                    except (ValueError, TypeError) as error:
                        result = {'content':[{'type':'text','text':str(error)}], 'isError':True}
                else:
                    return self.respond(200, {'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Method not found'}})
                self.respond(200, {'jsonrpc':'2.0','id':rid,'result':result})
            except (ValueError, TypeError):
                self.respond(400, {'jsonrpc':'2.0','id':rid,'error':{'code':-32600,'message':'Invalid request'}})
            except (TimeoutError, ConnectionError):
                return
            except Exception:
                self.respond(500, {'jsonrpc':'2.0','id':rid,'error':{'code':-32603,'message':'Intake unavailable; retry with the same report_id'}})

    return ThreadingHTTPServer((host,port),Handler)
