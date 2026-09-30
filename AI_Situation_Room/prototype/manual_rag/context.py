"""Search failures are visible; retrieval never writes incident facts."""
import json


def search_context(run, session, evidence):
    """Whole labeled fields only; no other sessions, history, or unapproved inbox."""
    candidates = []
    def add(label, value):
        if value not in (None, '', {}, []):
            candidates.append(json.dumps({label:value}, ensure_ascii=False))
    add('이번 실행의 시뮬레이션 가정 · 사실 아님', run.get('assumptions'))
    for key, value in session.get('facts', {}).items():
        add('현재 세션 사용자 기록 / '+key, value)
    for key, value in session.get('incident', {}).items():
        add('현재 사건 기록 / '+key, value)
    for item in evidence or []:
        if not item.get('id','').startswith('linkone:'): continue
        source = json.loads(item['content'])
        for key, value in source.get('room', {}).items():
            add('Link-One 수신 사건 / '+key, value)
        add('Link-One 수신 집계 · 기록 기준', source.get('summary'))
        # Distinct current states, excluding names/identities and historical events.
        states = {json.dumps(p['state'], ensure_ascii=False, sort_keys=True)
                  for p in source.get('people', []) if p.get('state') and p.get('included', True)}
        for state in sorted(states): add('Link-One 수신 현재 상태 · 사실 확인 필요', json.loads(state))
        for key, rows in source.get('current', {}).items():
            for row in rows: add('Link-One 수신 현재 기록 / '+key, row)
    parts, used, omitted = [], 0, 0
    for part in candidates:
        size = len(part.encode('utf-8'))
        if size > 2000 or used+size > 6000 or len(parts) >= 12:
            omitted += 1
        else:
            parts.append(part); used += size
    return parts, omitted


def prepare_manual_context(run, session, assignment, searcher, evidence=None):
    try:
        parts, omitted = search_context(run, session, evidence)
        result = searcher.retrieve(run['prompt'], role=assignment['role'],
            context_parts=parts, assignment=assignment['instruction'], budget_bytes=6000)
        result['context_omitted_fields'] = omitted
        if omitted:
            result['warnings'].append('context_omitted')
            if result['status'] in ('ok','no_match'): result['status'] = 'partial'
    except Exception:
        result = dict(status='error', reason='국제 매뉴얼 검색에 실패했습니다. 제공된 기본 자료만 검토하세요.',
                      generation=searcher.generation, method='unavailable', items=[], omitted_ids=[], warnings=[], latency_ms=0)
    return result


def combine_results(results):
    priority = {'ok':0, 'no_match':1, 'partial':2, 'unavailable':3, 'error':4}
    worst = max(results, key=lambda r: priority.get(r['status'], 4))
    return dict(status=worst['status'], reason=worst.get('reason',''), generation=worst['generation'],
                method=worst['method'], warnings=sorted({w for r in results for w in r['warnings']}),
                omitted_ids=sorted({i for r in results for i in r['omitted_ids']}),
                latency_ms=sum(r['latency_ms'] for r in results))


def with_manuals(context, result):
    evidence = {item['id']: item for item in context['evidence']}
    evidence.update({item['id']: item for item in result.get('items',[])})
    combined = dict(context, evidence=list(evidence.values()),
                    manual_search={k:v for k,v in result.items() if k != 'items'})
    return combined
