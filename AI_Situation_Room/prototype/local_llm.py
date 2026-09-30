"""LM Studio adapter: loopback only, explicit selection, no cloud fallback."""
import http.client
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from .models import ModelError, model_input

DEFAULT_MODEL='qwen/qwen3.6-35b-a3b'
DEFAULT_URL='http://127.0.0.1:1234/v1'


def local_config(data):
    url=data.get('base_url',DEFAULT_URL)
    model=data.get('model',DEFAULT_MODEL)
    if not isinstance(url,str) or not isinstance(model,str):raise ValueError('주소와 모델 이름을 확인하세요.')
    u=urllib.parse.urlsplit(url.strip())
    if u.scheme!='http' or u.hostname not in ('localhost','127.0.0.1','::1') or u.username or u.password or u.query or u.fragment or u.path.rstrip('/') not in ('','/v1'):
        raise ValueError('로컬 LM Studio의 http://127.0.0.1:포트 주소를 입력하세요.')
    port=u.port or 80
    if not 1<=port<=65535:raise ValueError('포트를 확인하세요.')
    model=model.strip()
    if not model or len(model)>200 or any(ord(c)<32 for c in model):raise ValueError('모델 ID를 확인하세요.')
    host='[::1]' if u.hostname=='::1' else '127.0.0.1'
    return {'provider':'local','base_url':f'http://{host}:{port}/v1','model':model}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def local_request(url,payload=None,timeout=5):
    request=urllib.request.Request(url,data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(request,timeout=timeout) as response:
            body=response.read(2_000_001)
        if len(body)>2_000_000:raise ValueError('response too large')
        data=json.loads(body)
        if not isinstance(data,dict):raise ValueError('response not object')
        return data
    except urllib.error.HTTPError as exc:
        raise ModelError(f'LM Studio 응답 오류 (HTTP {exc.code}). 모델 로드·문맥 길이·서버 설정을 확인하세요.',{'error_kind':'http','http_status':exc.code}) from None
    except (OSError,http.client.HTTPException) as exc:
        timed=isinstance(exc,TimeoutError) or isinstance(getattr(exc,'reason',None),TimeoutError)
        raise ModelError('LM Studio 응답 시간이 초과되었습니다. 저장된 입력은 유지됩니다.' if timed else 'LM Studio에 연결하지 못했습니다. 로컬 서버 실행과 포트를 확인하세요.',{'error_kind':'timeout' if timed else 'network'}) from None
    except (ValueError,UnicodeError):
        raise ModelError('LM Studio 응답 형식을 읽지 못했습니다.',{'error_kind':'invalid_response'}) from None


def probe(data):
    cfg=local_config(data)
    try:raw=local_request(cfg['base_url']+'/models')
    except ModelError as exc:raise ValueError(str(exc)) from None
    ids=[r.get('id') for r in raw.get('data',[]) if isinstance(r,dict) and isinstance(r.get('id'),str)]
    if cfg['model'] not in ids:raise ValueError('모델 목록에 지정한 ID가 없습니다. LM Studio에서 모델 ID를 확인하세요.')
    return {'ok':True,'model':cfg['model'],'message':'서버 연결·모델 ID 확인 완료. 실제 생성 품질·속도는 실행으로 확인합니다.'}


def output_schema(stage,context=None):
    string={'type':'string'};strings={'type':'array','items':string}
    question={'type':'object','properties':{'question':string,'reason':string,'priority':{'type':'string','enum':['high','medium','low']}},'required':['question','reason','priority'],'additionalProperties':False}
    order={'type':'object','properties':{'asset_id':string,'order':string,'reason':string,'priority':{'type':'string','enum':['high','medium','low']}},'required':['asset_id','order','reason','priority'],'additionalProperties':False}
    allowed=[e['id'] for e in (context or {}).get('evidence',[]) if isinstance(e.get('id'),str)]
    ids={'type':'array','items':{'type':'string','enum':allowed}} if allowed else {'type':'array','items':string,'maxItems':0}
    props={'summary':string,'dispatch_orders':{'type':'array','items':order}}
    if stage=='plan':
        props.update(questions={'type':'array','items':question},update={'type':'object'},tasks={'type':'array','maxItems':3,'items':{'type':'object','properties':{'role':{'type':'string','enum':['intel','sar','resource']},'instruction':string,'reason':string},'required':['role','instruction','reason'],'additionalProperties':False}})
    else:
        props.update(findings=strings,recommendation=string,uncertainties=strings,information_requests={'type':'array','items':question,'maxItems':2 if stage=='final' else 5},evidence_ids=ids)
    required=list(props)
    if stage!='plan':
        props['evidence_links']={'type':'array','maxItems':12,'items':{'type':'object','properties':{'claim':string,'application':string,'evidence_ids':ids,'limitations':strings},'required':['claim','application','evidence_ids','limitations'],'additionalProperties':False}}
    return {'type':'object','properties':props,'required':required,'additionalProperties':False}


class LocalModel:
    def __init__(self,data):
        self.config=local_config(data);self.model=self.config['model'];self.slot=threading.BoundedSemaphore(1)

    def respond(self,role,stage,context):
        queued=time.monotonic()
        with self.slot:
            started=time.monotonic()
            instructions,context,limit=model_input(role,stage,context)
            payload={'model':self.model,'messages':[{'role':'system','content':instructions+'\n최종 JSON만 출력하세요. /no_think'},{'role':'user','content':json.dumps({'context':context},ensure_ascii=False)+'\n/no_think'}],
                'response_format':{'type':'json_schema','json_schema':{'name':'haeon_'+stage,'strict':True,'schema':output_schema(stage,context)}},
                'max_tokens':limit,'temperature':0.2,'stream':False,'reasoning_effort':'none','chat_template_kwargs':{'enable_thinking':False}}
            raw=local_request(self.config['base_url']+'/chat/completions',payload,timeout=180)
            try:
                choice=raw['choices'][0]
                if choice.get('finish_reason')!='stop':raise ValueError('incomplete')
                # Reasoning is neither a user report nor a substitute for a missing final answer.
                content=choice['message']['content']
                result=json.loads(content)
                if not isinstance(result,dict):raise ValueError('not object')
            except (KeyError,IndexError,TypeError,ValueError):
                raise ModelError('로컬 모델의 최종 JSON이 비었거나 완료되지 않았습니다. LM Studio 추론 설정·출력 한도를 확인하세요.',{'error_kind':'invalid_or_incomplete'}) from None
            return result,{'model':raw.get('model',self.model),'usage':raw.get('usage'),'response_id':raw.get('id'),
                'diagnostics':{'phase':'completed','elapsed_ms':round((time.monotonic()-started)*1000,2),'queue_ms':round((started-queued)*1000,2),'timeout_seconds':180,'output_limit':limit,'input_chars':len(payload['messages'][1]['content']),'instruction_chars':len(instructions)}}
