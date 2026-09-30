"""Server-owned execution; UI polling never creates model calls."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from collections import deque
from contextlib import nullcontext
from .models import DemoModel, ResponsesModel, ModelError, MODEL, ROLES, effort
from .tools import evidence_for
from .store import Conflict
from . import local_llm
from .manuals import normalize_orders, recommended_dispatch, local_catalog_applies


class Engine:
    def __init__(self, store, demo_model=None, live_model=None, manual_search=None):
        self.store=store
        self.demo_model=demo_model or DemoModel()
        self.live_model=live_model or ResponsesModel()
        with store.db() as db:
            row=db.execute("SELECT value FROM settings WHERE key='llm'").fetchone()
        self.model_config=json.loads(row[0]) if row else {'provider':'openai','base_url':local_llm.DEFAULT_URL,'model':local_llm.DEFAULT_MODEL}
        self.local_model=local_llm.LocalModel(self.model_config) if self.model_config['provider']=='local' else None
        self._manual_search_service=manual_search
        with store.db() as db:
            setting=db.execute("SELECT value FROM settings WHERE key='manual_search_enabled'").fetchone()
        self.manual_search=manual_search if not setting or json.loads(setting[0]) else None
        self.pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='session')
        self.agents=ThreadPoolExecutor(max_workers=6,thread_name_prefix='agent')
        self.lock=threading.Lock()
        self.queues={}
        self.draining=set()
        self.futures={}
        self.slots=threading.BoundedSemaphore(6)

    def live_available(self):
        return self.model_config['provider']=='local' or bool(getattr(self.live_model,'key',None))

    def model_settings(self):
        return dict(self.model_config,openai_available=bool(getattr(self.live_model,'key',None)),live_available=self.live_available())

    def manual_settings(self):
        service=self._manual_search_service
        return {'enabled':self.manual_search is not None,
                'mode':self.manual_search.mode if self.manual_search else 'off',
                'ready_vector':bool(self.manual_search and self.manual_search.ready_vector),
                'available':bool(service and service.mode=='hybrid' and service.ready_vector)}

    def configure_manual_search(self,data):
        enabled=data.get('enabled')
        if type(enabled) is not bool:raise ValueError('매뉴얼 검색 켜기·끄기를 선택하세요.')
        with self.lock:
            with self.store.db() as db:
                runs=[json.loads(r[0]) for r in db.execute("SELECT data FROM objects WHERE kind='runs'")]
                if any(r.get('status') in ('queued','running') for r in runs):
                    raise Conflict('진행·대기 중인 분석이 있습니다. 완료 후 매뉴얼 검색을 변경하세요.')
                if enabled and not self.manual_settings()['available']:
                    raise Conflict('벡터 검색 환경이 준비되지 않았습니다. 검색 환경과 인덱스를 준비해 서버를 실행하세요.')
                db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('manual_search_enabled',?)",(json.dumps(enabled),))
            self.manual_search=self._manual_search_service if enabled else None
            return self.manual_settings()

    def configure_model(self,data):
        provider=data.get('provider')
        if provider not in ('openai','local'):raise ValueError('지원하지 않는 모델 연결입니다.')
        with self.lock:
            with self.store.db() as db:
                runs=[json.loads(r[0]) for r in db.execute("SELECT data FROM objects WHERE kind='runs'")]
            if any(r.get('status') in ('queued','running') for r in runs):raise Conflict('진행·대기 중인 AI 작업이 있습니다. 완료 후 모델을 전환하세요.')
            cfg=local_llm.local_config(data if provider=='local' else self.model_config)
            if provider=='local':local_llm.probe(cfg)
            elif not getattr(self.live_model,'key',None):raise Conflict('OpenAI API 키가 서버에 설정되어 있지 않습니다.')
            cfg['provider']=provider
            model=local_llm.LocalModel(cfg) if provider=='local' else None
            with self.store.db() as db:
                db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('llm',?)",(json.dumps(cfg),))
            self.model_config=cfg;self.local_model=model
            return self.model_settings()

    def submit(self, sid, prompt, kind, assumptions, request_id, inbox_report_id=None):
        with self.lock:
            if inbox_report_id:
                from .inbox import Inbox
                run=Inbox(self.store).enqueue(sid,inbox_report_id)
            else:
                run=self.store.enqueue(sid,prompt,kind,assumptions,request_id)
            if run['id'] not in self.futures and run['status']=='queued':
                run=self.store.update_run(run['id'],model_config=dict(self.model_config))
                self.futures[run['id']]=Future()
                self.queues.setdefault(sid,deque()).append(run['id'])
                if sid not in self.draining:
                    self.draining.add(sid)
                    self.pool.submit(self.drain,sid)
        return run

    def drain(self,sid):
        while True:
            with self.lock:
                if not self.queues[sid]:
                    self.draining.remove(sid)
                    del self.queues[sid]
                    return
                rid=self.queues[sid].popleft()
            try:
                self.process(rid)
                self.futures[rid].set_result(None)
            except Exception as exc:
                self.futures[rid].set_exception(exc)

    def wait(self, rid):
        self.futures[rid].result(timeout=30)

    def close(self):
        self.pool.shutdown(wait=True)
        self.agents.shutdown(wait=True)

    def call(self, run, role, stage, context, slot_held=False):
        started=time.time()
        provider=self.demo_model if run['mode']=='demo' else self.local_model if self.model_config['provider']=='local' else self.live_model
        local=run['mode']!='demo' and self.model_config['provider']=='local'
        requested=provider.model if local else MODEL
        provider_name='demo' if run['mode']=='demo' else 'local' if local else 'openai'
        try:
            if 'manual_search' in context:
                self.store.record_manual_context(run['session_id'],run['id'],stage,role,
                    context['manual_search'],[e for e in context['evidence'] if e['id'].startswith('sar:')])
            with (nullcontext() if slot_held else self.slots):
                result,metadata=provider.respond(role,stage,context)
            self.validate(result,stage,context)
            result['dispatch_orders']=normalize_orders(result.get('dispatch_orders',[]),context['session'])
            self.store.record_call(run['session_id'],run_id=run['id'],role=role,stage=stage,
                requested_model=requested,reasoning_effort='none' if local else effort(role),mode=run['mode'],provider=provider_name,
                status='completed',started_at=started,ended_at=time.time(),**metadata)
            return result
        except Exception as exc:
            self.store.record_call(run['session_id'],run_id=run['id'],role=role,stage=stage,
                requested_model=requested,reasoning_effort='none' if local else effort(role),mode=run['mode'],provider=provider_name,
                status='failed',started_at=started,ended_at=time.time(),diagnostics=getattr(exc,'diagnostics',{}))
            raise

    def validate(self, result, stage, context):
        if not isinstance(result,dict) or not isinstance(result.get('summary'),str) or not result['summary'].strip():
            raise ModelError('보고 요약이 누락되었습니다.')
        if len(json.dumps(result,ensure_ascii=False))>30000:
            raise ModelError('모델 응답이 표시 한도를 초과했습니다.')
        if stage=='plan':
            self.validate_requests(result.get('questions',[]),'상황실장')
            self.validate_dispatch_orders(result.get('dispatch_orders',[]))
            tasks=result.get('tasks')
            if not isinstance(tasks,list) or not 0<=len(tasks)<=3:
                raise ModelError('유효한 임무 배정이 필요합니다.')
            if not tasks and not result.get('update') and not result.get('questions'):
                raise ModelError('직접 처리에는 저장할 갱신 내용이 필요합니다.')
            roles=[]
            for t in tasks:
                if not isinstance(t,dict) or t.get('role') not in ('intel','sar','resource'):
                    raise ModelError('지원하지 않는 요원 배정입니다.')
                if any(not isinstance(t.get(k),str) or not t[k].strip() for k in ('instruction','reason')):
                    raise ModelError('임무와 배정 이유가 필요합니다.')
                roles.append(t['role'])
            if len(roles)!=len(set(roles)):raise ModelError('중복 요원 배정입니다.')
        else:
            for field in ('findings','uncertainties','evidence_ids'):
                if not isinstance(result.get(field),list) or any(not isinstance(x,str) for x in result[field]):
                    raise ModelError('보고 목록 형식이 잘못되었습니다.')
            if not isinstance(result.get('recommendation'),str):raise ModelError('권고 형식이 잘못되었습니다.')
            if set(result['evidence_ids'])-{e['id'] for e in context['evidence']}:
                raise ModelError('현재 세션에 없는 근거를 인용했습니다.')
            links=result.get('evidence_links',[])
            if not isinstance(links,list) or len(links)>12:
                raise ModelError('매뉴얼 근거 연결 형식이 잘못되었습니다.')
            matched=[];unmatched=[]
            for link in links:
                if not isinstance(link,dict) or any(not isinstance(link.get(k),str) or not link[k].strip() for k in ('claim','application')):
                    raise ModelError('매뉴얼 근거의 주장·적용 이유가 필요합니다.')
                ids=link.get('evidence_ids')
                if not isinstance(ids,list) or not ids or any(not isinstance(x,str) for x in ids) or set(ids)-set(result['evidence_ids']):
                    raise ModelError('매뉴얼 연결은 보고가 실제 인용한 근거만 사용할 수 있습니다.')
                if not isinstance(link.get('limitations'),list) or any(not isinstance(x,str) for x in link['limitations']):
                    raise ModelError('매뉴얼 적용 제한 형식이 잘못되었습니다.')
                # Optional attribution must never create or rewrite a report claim.
                target=matched if link['claim'] in [result['summary'],result['recommendation'],*result['findings']] else unmatched
                target.append(link)
            result.pop('unmatched_evidence_links',None)  # Server-owned exclusion record.
            if links:result['evidence_links']=matched
            if unmatched:
                result['unmatched_evidence_links']=unmatched
                result['uncertainties'].append('일부 문장별 매뉴얼 연결은 보고 문구와 불일치하여 제외했습니다. 해당 연결의 근거 적용은 확인이 필요합니다.')
            self.validate_dispatch_orders(result.get('dispatch_orders',[]))
            self.validate_requests(result.get('information_requests',[]),ROLES.get(context.get('assignment',{}).get('role','commander'),'상황실장'))

    @staticmethod
    def validate_requests(requests, source):
        if not isinstance(requests,list) or len(requests)>12:
            raise ModelError('추가 정보 요구 형식이 잘못되었습니다.')
        for item in requests:
            if not isinstance(item,dict) or any(not isinstance(item.get(k),str) or not item[k].strip()
                                                for k in ('question','reason')):
                raise ModelError(f'{source}의 정보 요구에는 질문과 이유가 필요합니다.')
            if 'priority' in item and (not isinstance(item['priority'],str) or not item['priority'].strip()):
                raise ModelError('정보 요구 우선순위 형식이 잘못되었습니다.')
            if 'source' in item and (not isinstance(item['source'],str) or not item['source'].strip()):
                raise ModelError('정보 요구 출처 형식이 잘못되었습니다.')

    @staticmethod
    def information_requests(items, source):
        result=[]
        for item in items or []:
            if not isinstance(item,dict) or not item.get('question') or not item.get('reason'):
                continue
            result.append({'question':item['question'].strip(), 'reason':item['reason'].strip(),
                           'priority':item.get('priority','medium'), 'source':item.get('source') or source})
        return result

    @staticmethod
    def validate_dispatch_orders(orders):
        if not isinstance(orders,list) or len(orders)>20:
            raise ModelError('출동 지시안 형식이 잘못되었습니다.')
        for item in orders:
            if not isinstance(item,dict) or not isinstance(item.get('asset_id'),str) or not item['asset_id'].strip():
                raise ModelError('출동 지시안에는 가용세력 ID가 필요합니다.')
            for key in ('order','reason'):
                if not isinstance(item.get(key),str) or not item[key].strip():
                    raise ModelError('출동 지시안에는 지시 내용과 이유가 필요합니다.')

    @staticmethod
    def dispatch_orders(model_orders, manual_orders, session=None):
        result=[]
        for item in normalize_orders(manual_orders,session)+normalize_orders(model_orders,session):
            if item['asset_id'] not in {order['asset_id'] for order in result}:
                result.append(item)
        return result

    def agent(self, run, assignment, context):
        task=self.store.add_task(run,assignment['role'],assignment['instruction'],assignment['reason'])
        try:
            with self.slots:
                self.store.update_task(task['id'],status='running',started_at=time.time())
                self.store.event(run['session_id'],ROLES[task['role']]+'에게 지시',run_id=run['id'],task_id=task['id'])
                report=self.call(run,task['role'],'report',dict(context,assignment=assignment),slot_held=True)
            self.store.update_task(task['id'],status='completed',ended_at=time.time(),report=report)
            self.store.event(run['session_id'],ROLES[task['role']]+' 보고 수신',run_id=run['id'],task_id=task['id'])
            if report.get('information_requests'):
                self.store.event(run['session_id'],ROLES[task['role']]+' → 상황실장 추가 정보 요구',run_id=run['id'],
                                 task_id=task['id'],information_requests=report['information_requests'])
            return {'id':task['id'],'role':task['role'],'report':report}
        except Exception as exc:
            error=str(exc) if isinstance(exc,(ModelError,ValueError)) else '요원 처리 중 오류가 발생했습니다. 새 요청으로 재검토하세요.'
            self.store.update_task(task['id'],status='failed',ended_at=time.time(),error=error)
            self.store.event(run['session_id'],ROLES[task['role']]+' 작업 실패',run_id=run['id'],task_id=task['id'])
            raise

    def process(self, rid):
        run=self.store.get_run(rid)
        sid=run['session_id']
        try:
            snap=self.store.snapshot(sid)
            run=self.store.update_run(rid,status='running',started_at=time.time(),
                based_on_version=snap['session']['version'])
            if self.manual_search:
                self.store.update_run(rid,manual_search={'status':'not_requested','generation':self.manual_search.generation})
            # Only prior/current turns, never future queued user requests.
            ordered_runs=[r['id'] for r in snap['runs']]
            previous_ids=ordered_runs[:ordered_runs.index(rid)+1]
            history=[m for prior_id in previous_ids for m in snap['messages'] if m.get('run_id')==prior_id]
            snap['messages']=history
            context={'session':snap['session'],'request':run,'history':history,
                     'evidence':evidence_for(snap,run['prompt'])}
            if snap['session'].get('linkone'):
                req=run['request_id']
                context['review_purpose']=('initial_baseline' if snap['session']['linkone'].get('revision')==1 else 'changed_snapshot') if req.startswith('linkone:') else ('reanalysis' if req.startswith('linkone-review:') else 'user_question')
            if len(json.dumps(context,ensure_ascii=False))>180000:
                raise ModelError('세션이 초기 프로토타입의 입력 한도를 초과했습니다. 새 세션을 사용하세요. 기존 기록은 보존됩니다.')
            self.store.event(sid,'상황실장 · 요청 해석과 임무 배정',run_id=rid)
            # External claims and their summaries cannot become ordinary fact-update inputs.
            plan_history=history if run.get('external_report_id') else [m for m in history if not m.get('external_report_id') and not m.get('external_report_ids')]
            plan_evidence=context['evidence'] if run.get('external_report_id') else [e for e in context['evidence'] if not e.get('external_report_id')]
            plan_context=dict(context,history=plan_history,evidence=plan_evidence)
            if run['mode']=='live':
                plan_context=dict(plan_context,history=[{'role':m['role'],'content':m['content'],'external_report_id':m.get('external_report_id')} for m in plan_history[-4:]],
                    evidence=[e for e in plan_evidence if e['id'] in ('facts','incident','weather') or e['id'] in [m['id'] for m in history[-4:]] or e['title']!='사용자 신고 원문'])
            decision=self.call(run,'commander','plan',plan_context)
            if snap['session'].get('linkone'):
                decision['update']={}
                if not decision.get('tasks'):
                    decision['tasks']=[{'role':'intel','instruction':'현재 링크온 수신본과 변경사항을 검토하고 근거와 미확인 사항을 보고하세요.','reason':'링크온 전용 세션은 원본을 수정하지 않고 분석합니다.'}]
            if run.get('external_report_id'):
                decision['update']={}
                if not decision.get('tasks'):
                    decision['tasks']=[{'role':'intel','instruction':'인용된 외부 보고를 미확인 주장으로 검토하고 근거와 추가 확인사항을 보고하세요.',
                                       'reason':'담당자가 외부 보고의 검토를 요청했습니다.'}]
                self.store.event(sid,'외부 보고 인용 검토 · 사실 자동 반영 없음',event_type='external_review',run_id=rid,
                                 external_report_id=run['external_report_id'])
            decision['questions']=self.information_requests(decision.get('questions',[]),'상황실장')
            decision['dispatch_orders']=self.dispatch_orders(decision.get('dispatch_orders',[]),
                                                              recommended_dispatch(run['prompt'],context['session']),context['session'])
            self.store.update_run(rid,decision=decision)
            if decision['questions']:
                self.store.event(sid,'상황실장 → 사용자 추가 정보 요구',run_id=rid,
                                 information_requests=decision['questions'])
            if decision['dispatch_orders']:
                self.store.event(sid,'상황실장 → 가용세력 출동 지시안 제시',run_id=rid,
                                 dispatch_orders=decision['dispatch_orders'])
            patch=decision.get('update')
            if patch and run['kind']!='simulation' and not run.get('external_report_id'):
                session=self.store.apply_update(rid,patch,run['based_on_version'])
                run=self.store.get_run(rid)
                context=dict(context,session=session,request=run)
                snap['session']=session
                context['evidence']=evidence_for(snap,run['prompt'])
            if not decision['tasks']:
                from .incident import receipt
                source_id=run.get('source_id') or next(m['id'] for m in history if m.get('role')=='user')
                final=receipt(context['session'],source_id,decision['summary'],decision['questions'],decision['dispatch_orders'])
                self.store.update_run(rid,decision=decision)
                self.store.finish_run(rid,final)
                return
            if run['mode']=='live':
                context['history']=[]
            agent_context=context
            if run['mode']=='live':
                latest=history[-1]['id']
                agent_context=dict(context,evidence=[e for e in context['evidence'] if e['id']==latest or e['title']!='사용자 신고 원문'])
            self.store.update_run(rid,decision=decision)
            specialist_contexts=[agent_context for _ in decision['tasks']]
            if self.manual_search:
                from .manual_rag.context import prepare_manual_context, with_manuals, combine_results
                results=[prepare_manual_context(run,context['session'],a,self.manual_search,
                         evidence=context['evidence']) for a in decision['tasks']]
                specialist_contexts=[with_manuals(agent_context,r) for r in results]
                combined=combine_results(results)
                combined['items']=list({e['id']:e for r in results for e in r['items']}.values())
                agent_context=with_manuals(agent_context,combined)
                context=with_manuals(context,combined)
                self.store.update_run(rid,manual_search=context['manual_search'])
            futures=[self.agents.submit(self.agent,run,a,c) for a,c in zip(decision['tasks'],specialist_contexts)]
            reports=[]
            failure=None
            for f in futures:
                try: reports.append(f.result())
                except Exception as exc: failure=exc
            if failure:raise failure
            critic={'role':'critic','instruction':'수신 보고의 근거 누락·모순·가정 혼동을 점검하세요.',
                    'reason':'종합 전에 보고의 불확실성과 충돌을 확인합니다.'}
            reports.append(self.agent(run,critic,dict(agent_context,reports=list(reports))))
            self.store.event(sid,'상황실장 · 보고 종합과 최종 조언',run_id=rid)
            final=self.call(run,'commander','final',dict(context,reports=reports,
                                                        dispatch_orders=decision['dispatch_orders']))
            if any(r['report'].get('unmatched_evidence_links') for r in reports):
                final['uncertainties'].append('요원 보고의 일부 문장별 매뉴얼 연결이 불일치하여 제외됐습니다. 원 보고의 제외 이력을 확인하세요. 이 연결은 근거 검증 완료로 취급하지 않습니다.')
            requests=self.information_requests(decision.get('questions',[]),'상황실장')
            for item in reports:
                requests.extend(self.information_requests(item['report'].get('information_requests',[]),ROLES[item['role']]))
            requests.extend(self.information_requests(final.get('information_requests',[]),'상황실장'))
            dedup=[];seen=set()
            for item in requests:
                key=item['question']
                if key not in seen:
                    seen.add(key);dedup.append(item)
            if context['session'].get('linkone') or (run['mode']=='live' and run.get('model_config',{}).get('provider')=='local'):
                # The existing synthesis call selects/merges questions; keep agent originals in tasks.
                selected=self.information_requests(final.get('information_requests',[]),'상황실장')
                selected.sort(key=lambda q:{'high':0,'medium':1,'low':2}.get(q['priority'],1))
                dedup=list({q['question']:q for q in selected}.values())[:2]
            final['information_requests']=dedup
            final['dispatch_orders']=self.dispatch_orders(final.get('dispatch_orders',[]),decision['dispatch_orders'],context['session'])
            if dedup:
                self.store.event(sid,'추가 정보 요구 · 사용자 확인 필요',run_id=rid,
                                 information_requests=dedup)
            final['timeline']=[{'text':m['content'],'source_id':m['id'],'received_at':m['created_at']} for m in history if m['role']=='user' and m.get('kind')!='simulation']
            final['report_ids']=[r['id'] for r in reports]
            final['external_report_ids']=sorted({e['external_report_id'] for e in context['evidence'] if e.get('external_report_id')})
            final['linkone_snapshot_id']=run.get('linkone_snapshot_id')
            final['basis_version']=run['based_on_version']
            final['assumptions']=run['assumptions']
            self.store.finish_run(rid,final)
        except Exception as exc:
            message=str(exc) if isinstance(exc,(ModelError,ValueError)) else '작업 처리 중 오류가 발생했습니다. 저장된 입력을 확인하고 다시 요청하세요.'
            self.store.finish_run(rid,None,status='failed',error=message)
