"""Loopback-only prototype server. Run: python3 -m prototype.server"""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from .store import Store, Conflict
from .engine import Engine
from .inbox import Inbox
from .models import MODEL, ROLES, effort
from .tools import weather
from .manuals import manual_evidence

STATIC=Path(__file__).parent/'static'


def make_server(store,engine,port=8860,mcp_enabled=False):
    inbox=Inbox(store)
    token=secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def send_json(self,status,data):
            self.respond(status,json.dumps(data,ensure_ascii=False,allow_nan=False).encode(),'application/json; charset=utf-8')

        def respond(self,status,body,content_type):
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers();self.wfile.write(body)

        def permitted(self,write=False):
            hosts={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            if self.headers.get('Host') not in hosts:return False
            origin=self.headers.get('Origin')
            if origin and origin not in {'http://'+h for h in hosts}:return False
            return not write or secrets.compare_digest(self.headers.get('X-Session-Token',''),token)

        def do_GET(self):
            if not self.permitted():return self.send_json(403,{'error':'허용되지 않은 접근입니다.'})
            path=urlparse(self.path).path
            try:
                if path=='/api/config':
                    return self.send_json(200,{'token':token,'live_available':bool(os.environ.get('OPENAI_API_KEY')),
                        'profiles':{r:{'name':n,'model':MODEL,'effort':effort(r)} for r,n in ROLES.items()},
                        'capabilities':{'sessions':True,'parallel':True,'csv':True,'lexical_search':True,
                        'vector_search':False,'mcp':mcp_enabled,'inbox':True,'weather_scheduler':False}})
                if path=='/api/inbox':return self.send_json(200,inbox.list())
                if path=='/api/manuals':return self.send_json(200,manual_evidence())
                if path=='/api/sessions':return self.send_json(200,store.list_sessions())
                if path=='/api/monitor':return self.send_json(200,{'session_id':store.pinned()})
                pieces=path.strip('/').split('/')
                if len(pieces)==3 and pieces[:2]==['api','sessions']:
                    return self.send_json(200,store.snapshot(pieces[2]))
                static={'/':'index.html','/monitor':'index.html','/app.js':'app.js','/inbox.js':'inbox.js','/style.css':'style.css'}.get(path)
                if static:
                    content=(STATIC/static).read_bytes()
                    mime=mimetypes.guess_type(static)[0] or 'application/octet-stream'
                    return self.respond(200,content,mime+'; charset=utf-8')
                return self.send_json(404,{'error':'경로를 찾을 수 없습니다.'})
            except KeyError as exc:return self.send_json(404,{'error':str(exc).strip("'")})
            except Exception:return self.send_json(500,{'error':'상태 조회 실패. 서버 실행 상태를 확인하세요.'})

        def do_POST(self):
            if not self.permitted(True):return self.send_json(403,{'error':'허용되지 않은 쓰기 요청입니다.'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=220000:raise ValueError('요청 크기를 확인하세요. 최대 220KB입니다.')
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    raise ValueError('JSON 요청이 필요합니다.')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('JSON 객체가 필요합니다.')
                path=urlparse(self.path).path
                if path=='/api/sessions':
                    mode=data.get('mode','demo')
                    if mode=='live' and not os.environ.get('OPENAI_API_KEY'):
                        raise Conflict('실제 AI 모드는 서버 OPENAI_API_KEY 설정 후 사용할 수 있습니다.')
                    return self.send_json(201,store.create_session(data.get('title'),mode))
                parts=path.strip('/').split('/')
                if len(parts)!=4 or parts[:2]!=['api','sessions']:
                    return self.send_json(404,{'error':'쓰기 경로가 없습니다.'})
                sid,action=parts[2:]
                store.snapshot(sid)
                if action=='message':
                    result=engine.submit(sid,data.get('prompt'),data.get('kind','analysis'),
                                         data.get('assumptions',''),data.get('request_id'),data.get('inbox_report_id'))
                    return self.send_json(202,result)
                if action=='inbox-link':return self.send_json(200,inbox.link(sid,data.get('project'),data.get('incident_id')))
                if action=='inbox-action':return self.send_json(200,inbox.act(sid,data.get('report_id'),data.get('action')))
                if action=='facts':return self.send_json(200,store.set_facts(sid,data.get('facts'),data.get('version')))
                if action=='attachments':return self.send_json(201,store.add_attachment(sid,data.get('name'),data.get('content')))
                if action=='pin':
                    store.pin(sid);return self.send_json(200,{'session_id':sid})
                if action=='delete':
                    return self.send_json(200,store.delete_session(sid))
                if action=='weather':
                    session=store.snapshot(sid)['session'];facts=session['facts']
                    if facts.get('lat') is None or facts.get('lon') is None:raise ValueError('상황 수정에서 위도·경도를 입력하세요.')
                    try:result=weather(facts['lat'],facts['lon'])
                    except Exception:
                        store.event(sid,'기상 조회 실패 · 기존 자료 유지',event_type='weather_failed')
                        return self.send_json(502,{'error':'기상 조회 실패. 기존 자료를 유지하며 재조회할 수 있습니다.'})
                    store.set_weather(sid,session['version'],result)
                    return self.send_json(200,result)
                return self.send_json(404,{'error':'쓰기 경로가 없습니다.'})
            except Conflict as exc:return self.send_json(409,{'error':str(exc)})
            except KeyError as exc:return self.send_json(404,{'error':str(exc).strip("'")})
            except (ValueError,TypeError) as exc:return self.send_json(400,{'error':str(exc) or '입력 형식을 확인하세요.'})
            except Exception:return self.send_json(500,{'error':'요청 처리 실패. 저장 상태를 확인한 뒤 다시 시도하세요.'})

    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main():
    parser=argparse.ArgumentParser(description='AI situation room local prototype')
    parser.add_argument('--port',type=int,default=8860)
    parser.add_argument('--db',default=str(Path(__file__).parent/'runtime'/'room.sqlite'))
    parser.add_argument('--mcp-port',type=int,help='설정할 때만 MCP listener 활성화 (예: 8862)')
    parser.add_argument('--mcp-host',default='127.0.0.1')
    parser.add_argument('--mcp-allowed-host',action='append',default=[])
    parser.add_argument('--mcp-tokens',default=str(Path(__file__).parent/'.secrets'/'mcp'/'clients.json'))
    args=parser.parse_args()
    store=Store(args.db);store.recover();engine=Engine(store)
    mcp=None
    if args.mcp_port is not None:
        from .mcp_server import make_mcp_server, load_tokens
        mcp=make_mcp_server(Inbox(store),load_tokens(args.mcp_tokens),args.mcp_host,args.mcp_port,args.mcp_allowed_host)
    server=make_server(store,engine,args.port,mcp_enabled=mcp is not None)
    if mcp:
        threading.Thread(target=mcp.serve_forever,daemon=True).start()
        print(f'MCP 수신: {args.mcp_host}:{mcp.server_port}/mcp · 담당자 승인 후 검토',flush=True)
    print(f'AI 상황실: http://127.0.0.1:{server.server_port}',flush=True)
    print('Live API: '+('configured' if os.environ.get('OPENAI_API_KEY') else 'not configured · demo available'),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        if mcp: mcp.shutdown();mcp.server_close()
        server.server_close();engine.close()


if __name__=='__main__':main()
