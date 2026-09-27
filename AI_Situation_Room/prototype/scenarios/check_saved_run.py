"""Verify persisted snapshots from the user-provided Cheonghae scenario; no API calls."""
import json
import re
import sys
from pathlib import Path

def verify(path):
    data=json.loads(Path(path).read_text());steps=data['steps']
    assert len(steps)==15,'15단계 실행 필요'
    assert all(x['run']['status']=='completed' for x in steps),'실패한 실행 있음'
    for n,total,rescued,remaining in [(2,7,0,7),(5,8,0,8),(7,8,3,5),(9,8,6,2),(12,8,8,0),(15,8,8,0)]:
        f=steps[n-1]['snapshot']['session']['facts']
        assert (f['total'],f['rescued'],f['remaining'])==(total,rescued,remaining),f'{n}단계 집계 불일치'
    before=steps[9]['snapshot']['session']['incident']['roster'];after=steps[10]['snapshot']['session']['incident']['roster']
    pid=next(k for k,v in before.items() if v.get('name')=='이기란')
    assert after[pid]=={**before[pid],'name':'이기관'},'동일 인물 이름만 정정 필요'
    assert steps[10]['run']['final']['report_ids']==[],'단순 정정에서 요원 재호출'
    final=steps[-1]['snapshot'];state=final['session'];incident=state['incident'];distribution=incident['distribution']
    assert sum(distribution.values())==8,'재이송 중 중복 집계'
    assert sum(n for p,n in distribution.items() if '301' in p)==5,'301함 5명'
    assert sum(n for p,n in distribution.items() if '묵호항' in p)==3,'묵호항 3명'
    assert sum(n for p,n in distribution.items() if '동진' in p or '청해' in p)==0,'원선박/지원선 잔류 0명'
    assert any(a.get('own_crew')==3 for a in incident['assets'].values() if '동진' in a.get('name','')),'자체승선원 별도 유지'
    patients=list(incident['patients'].values())
    assert sum(p['count'] for p in patients)==3,'환자 중복 집계'
    assert sum(p['count'] for p in patients if '묵호항' in p.get('location','') and re.search(r'인계.*완료',p.get('status','')))==2,'구급대 인계 2명'
    assert sum(p['count'] for p in patients if '301' in p.get('location','') and '진료' in p.get('status','') and '예정' in p.get('status',''))==1,'301함 진료 예정 1명'
    assert any('종료' in a.get('status','') for a in incident['assets'].values() if '동진' in a.get('name','')),'동진호 지원 종료 누락'
    assert incident['report_time']=='14:50','최신 명시 시각'
    report=steps[-1]['run']['final']
    texts=[e['text'] for e in report['timeline']]
    deduplicated=[v for i,v in enumerate(texts) if i==0 or v!=texts[i-1]]
    assert deduplicated==[e['run']['prompt'] for e in steps],'원문 경과 누락/순서 불일치'
    assert len(texts)==15+len(data.get('rejected_attempts',[])),'재시도 포함 원문 수 불일치'
    assert '예인' in report['summary'] and '침수' in report['summary'],'최종 주요 위험 누락'
    assert len(final['messages'])==30+len(data.get('rejected_attempts',[])),'메시지 수 불일치'
    return {'session_id':data['session_id'],'steps':15,'result':'PASS','version':state['version'],'calls':len(final['calls'])}

if __name__=='__main__':
    print(json.dumps(verify(sys.argv[1]),ensure_ascii=False))
