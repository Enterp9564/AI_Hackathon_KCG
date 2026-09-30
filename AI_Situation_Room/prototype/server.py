"""Loopback-only prototype server. Run: python3 -m prototype.server"""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .store import Store, Conflict
from .engine import Engine
from .inbox import Inbox
from .models import MODEL, ROLES, effort
from .tools import weather
from .manuals import manual_evidence

STATIC=Path(__file__).parent/'static'


def make_server(store,engine,port=8860,mcp_enabled=False,linkone_source=None,alert_source=None):
    from .linkone_sync import LinkOneSync
    linkone=LinkOneSync(store,engine,linkone_source)
    inbox=Inbox(store)
    from .patient_alerts import PatientAlerts
    # Injected legacy test sources must never open a real external connection.
    alerts=PatientAlerts(store,alert_source,start=False)
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
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src https://114-110-181-118.sslip.io; frame-ancestors 'none'; base-uri 'none'")
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
                    return self.send_json(200,{'token':token,'live_available':engine.live_available(),'llm':engine.model_settings(),
                        'manual_search':engine.manual_settings(),
                        'profiles':{r:{'name':n,'model':MODEL,'effort':effort(r)} for r,n in ROLES.items()},
                        'capabilities':{'sessions':True,'parallel':True,'csv':True,'lexical_search':True,
                        'vector_search':bool(engine.manual_search and engine.manual_search.ready_vector),'mcp':mcp_enabled,'inbox':True,'linkone':True,'weather_scheduler':False}})
                if path=='/api/settings/llm':return self.send_json(200,engine.model_settings())
                if path=='/api/settings/manual-search':return self.send_json(200,engine.manual_settings())
                if path=='/api/linkone/rooms':return self.send_json(200,linkone.rooms())
                if path=='/api/inbox':return self.send_json(200,inbox.list())
                if path=='/api/manuals':return self.send_json(200,manual_evidence())
                if path=='/api/sessions':return self.send_json(200,store.list_sessions())
                if path=='/api/monitor':return self.send_json(200,{'session_id':store.pinned()})
                pieces=path.strip('/').split('/')
                if len(pieces)==7 and pieces[:2]==['api','sessions'] and pieces[3]=='runs' and pieces[5]=='manual-contexts':
                    return self.send_json(200,store.get_manual_context(pieces[2],pieces[4],pieces[6]))
                if len(pieces)==4 and pieces[:2]==['api','manual-sources'] and pieces[3]=='pdf':
                    from .manual_rag.corpus import Corpus, CorpusError, digest
                    expected=parse_qs(urlparse(self.path).query).get('sha256',[''])[0]
                    try:corpus=engine.manual_search.corpus if engine.manual_search else Corpus()
                    except CorpusError:return self.send_json(409,{'error':'요청한 판본의 원본을 검증할 수 없습니다. 저장된 요약은 유지됩니다.'})
                    source=corpus.sources.get(pieces[2])
                    if not source:return self.send_json(404,{'error':'등록된 공개 매뉴얼이 아닙니다.'})
                    if expected!=source['original_sha256']:
                        return self.send_json(409,{'error':'요청한 판본의 원본이 없습니다. 최신 PDF로 대체하지 않습니다.'})
                    original=(corpus.root/source['original_path']).resolve()
                    if not original.is_relative_to(corpus.root.resolve()):return self.send_json(409,{'error':'원본 경로를 검증할 수 없습니다.'})
                    try:body=original.read_bytes()
                    except OSError:return self.send_json(409,{'error':'요청한 판본의 원본 파일이 없습니다.'})
                    if digest(body)!=expected:return self.send_json(409,{'error':'원본 PDF가 실행 당시 판본과 다릅니다. 저장된 요약은 유지됩니다.'})
                    return self.respond(200,body,'application/pdf')
                if len(pieces) in (4,5) and pieces[:2]==['api','sessions']:
                    if len(pieces)==4 and pieces[3]=='patient-alerts':return self.send_json(200,alerts.view(pieces[2]))
                    if pieces[3]=='linkone-history':return self.send_json(200,linkone.history(pieces[2]))
                    if pieces[3]=='linkone':return self.send_json(200,linkone.details(pieces[2],pieces[4] if len(pieces)==5 else None))
                if len(pieces)==3 and pieces[:2]==['api','sessions']:
                    return self.send_json(200,dict(store.snapshot(pieces[2]),llm=engine.model_settings()))
                static={'/':'index.html','/monitor':'index.html','/app.js':'app.js','/model-settings.js':'model-settings.js','/manuals.js':'manuals.js','/alert-list.js':'alert-list.js','/patient-alerts.js':'patient-alerts.js','/inbox.js':'inbox.js','/linkone.js':'linkone.js','/linkone-workspace.js':'linkone-workspace.js','/style.css':'style.css'}.get(path)
                if static:
                    content=(STATIC/static).read_bytes()
                    mime=mimetypes.guess_type(static)[0] or 'application/octet-stream'
                    return self.respond(200,content,mime+'; charset=utf-8')
                return self.send_json(404,{'error':'경로를 찾을 수 없습니다.'})
            except Conflict as exc:return self.send_json(409,{'error':str(exc)})
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
                if path=='/api/settings/llm/test':
                    from .local_llm import probe
                    return self.send_json(200,probe(data))
                if path=='/api/settings/llm':return self.send_json(200,engine.configure_model(data))
                if path=='/api/settings/manual-search':return self.send_json(200,engine.configure_manual_search(data))
                if path in ('/api/sessions','/api/linkone/connect'):
                    mode=data.get('mode','demo')
                    if mode=='live' and not engine.live_available():
                        raise Conflict('설정에서 로컬 LLM을 연결하거나 서버에 OpenAI API 키를 설정하세요.')
                    if path=='/api/linkone/connect':return self.send_json(202,linkone.connect(data.get('room_id'),mode))
                    return self.send_json(201,store.create_session(data.get('title'),mode))
                parts=path.strip('/').split('/')
                if len(parts)!=4 or parts[:2]!=['api','sessions']:
                    return self.send_json(404,{'error':'쓰기 경로가 없습니다.'})
                sid,action=parts[2:]
                store.snapshot(sid)
                if action=='linkone-sync':return self.send_json(202,linkone.sync(sid))
                if action=='linkone-analyze':return self.send_json(202,linkone.analyze(sid))
                if action=='patient-alert-seen':return self.send_json(200,alerts.seen(sid,data.get('alert_id')))
                if action=='vessel-alert-seen':return self.send_json(200,alerts.vessels.seen(sid,data.get('alert_id')))
                if action=='patient-alert-review':
                    quoted=alerts.quote(sid,data.get('alert_id'))
                    result=engine.submit(sid,**quoted)
                    alerts.seen(sid,data.get('alert_id'))
                    return self.send_json(202,result)
                if action=='message':
                    if str(data.get('request_id','')).startswith('patient-alert:'):
                        raise ValueError('환자 알림 인용은 알림 상세에서 요청하세요.')
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

    class Server(ThreadingHTTPServer):
        def server_close(self):
            super().server_close()
            alerts.close()
            linkone.close()
    try:server=Server(('127.0.0.1',port),Handler)
    except Exception:
        alerts.close();linkone.close();raise
    if alert_source is not None or linkone_source is None:alerts.start()
    server.linkone=linkone
    server.patient_alerts=alerts
    return server


def main():
    parser=argparse.ArgumentParser(description='AI situation room local prototype')
    parser.add_argument('--port',type=int,default=8860)
    parser.add_argument('--db',default=str(Path(__file__).parent/'runtime'/'room.sqlite'))
    parser.add_argument('--manual-search',choices=('off','lexical','hybrid'),default='off')
    parser.add_argument('--manual-index',help='명시적으로 준비한 로컬 SAR 인덱스 세대 폴더')
    parser.add_argument('--mcp-port',type=int,help='설정할 때만 MCP listener 활성화 (예: 8862)')
    parser.add_argument('--mcp-host',default='127.0.0.1')
    parser.add_argument('--mcp-allowed-host',action='append',default=[])
    parser.add_argument('--mcp-tokens',default=str(Path(__file__).parent/'.secrets'/'mcp'/'clients.json'))
    args=parser.parse_args()
    manual_search=None
    if args.manual_search!='off':
        from .manual_rag.retrieval import ManualSearch
        try:manual_search=ManualSearch(mode=args.manual_search,index_dir=args.manual_index)
        except ValueError:
            parser.error('국제 매뉴얼 무결성 확인 실패. 자료를 확인하거나 --manual-search off로 시작하세요.')
    store=Store(args.db);store.recover();engine=Engine(store,manual_search=manual_search)
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
        if manual_search:manual_search.close()


if __name__=='__main__':main()
