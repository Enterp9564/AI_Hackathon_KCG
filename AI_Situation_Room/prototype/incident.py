"""Validated partial updates to reported incident state; never inferred physical truth."""
from copy import deepcopy

FACTS={'total','rescued','remaining','location','lat','lon','notes'}
SECTIONS={'roster':{'name','role','location','condition','lifejacket'},
          'patients':{'kind','count','location','status'},
          'assets':{'name','own_crew','status'}}

def count(value):
    if type(value) is not int or not 0<=value<=100000:
        raise ValueError('인원은 0 이상의 정수여야 합니다.')

def string(value):
    if not isinstance(value,str) or not value.strip() or len(value)>2000:
        raise ValueError('상황 문자열 형식을 확인하세요.')

def merge_update(session, patch):
    if not isinstance(patch,dict) or set(patch)-{'facts','roster','patients','assets','distribution','conditions','vessel','report_time'}:
        raise ValueError('지원하지 않는 상황 갱신 항목입니다.')
    result=deepcopy(session);facts=result.setdefault('facts',{});incident=result.setdefault('incident',{})
    for section,values in patch.items():
        if section in ('vessel','report_time'):
            string(values);incident[section]=values;continue
        if not isinstance(values,dict):raise ValueError('상황 항목은 객체여야 합니다.')
        if section=='distribution':incident[section]={}
        target=facts if section=='facts' else incident.setdefault(section,{})
        for key,value in values.items():
            string(key)
            if section=='facts':
                if key not in FACTS:raise ValueError('지원하지 않는 사실 필드입니다.')
                if key in ('total','rescued','remaining'):count(value)
                elif key in ('lat','lon'):
                    import math
                    if type(value) not in (float,int) or not math.isfinite(value) or abs(value)>(90 if key=='lat' else 180):raise ValueError('좌표 범위 오류')
                else:string(value)
                target[key]=value
            elif section in SECTIONS:
                if not isinstance(value,dict) or set(value)-SECTIONS[section]:raise ValueError('명부/환자/자원 필드 오류')
                entry=target.setdefault(key,{})
                for field,item in value.items():
                    count(item) if field in ('count','own_crew') else string(item)
                    entry[field]=item
            elif section=='distribution':count(value);target[key]=value
            elif section=='conditions':string(value);target[key]=value
    import re
    for pid,change in patch.get('roster',{}).items():
        old=session.get('incident',{}).get('roster',{}).get(pid,{}).get('name')
        new=change.get('name')
        if old and new and old!=new and facts.get('notes'):
            facts['notes']=re.sub(r'(?<!\w)'+re.escape(old)+r'(?=\W|$)',lambda m:new,facts['notes'])
    total=facts.get('total')
    if total is not None:
        for field in ('rescued','remaining'):
            if facts.get(field,0)>total:raise ValueError('인원 집계가 총원을 초과합니다.')
        if 'rescued' in facts and 'remaining' in facts and facts['rescued']+facts['remaining']>total:
            raise ValueError('구조·잔류 인원이 총원을 초과합니다.')
        distribution=incident.get('distribution',{})
        if distribution and sum(distribution.values())!=total:
            raise ValueError('위치별 인원 합계가 총원과 다릅니다. 신고 내용을 확인하세요.')
        if sum(v.get('count',0) for v in incident.get('patients',{}).values())>total:
            raise ValueError('환자 수가 총원을 초과합니다.')
    return result


def receipt(session, source_id, summary, information_requests=None, dispatch_orders=None):
    f=session['facts'];i=session.get('incident',{})
    details=[]
    if f:details.append('현재 신고 집계: '+ ' / '.join(f'{label} {f[key]}명' for key,label in [('total','총원'),('rescued','구조'),('remaining','선내 잔류')] if key in f))
    for place,n in i.get('distribution',{}).items():
        details.append(f'{place}: 사건 대상자 {n}명')
    for p in i.get('roster',{}).values():details.append('명부: '+' · '.join(p.values()))
    for p in i.get('patients',{}).values():details.append('환자: '+' · '.join(str(v) for v in p.values()))
    for k,v in i.get('conditions',{}).items():details.append(f'{k}: {v}')
    for a in i.get('assets',{}).values():details.append('자원: '+' · '.join(str(v) for v in a.values()))
    for order in dispatch_orders or []:
        details.append('출동 지시안: '+ ' · '.join(str(order.get(key,'')) for key in ('asset_name','order','reason')))
    return dict(summary=summary,findings=details,
                recommendation=('위 정보가 확인되면 다음 판단을 갱신하겠습니다.' if information_requests else
                                '사용자 보고를 저장했습니다. 새로운 상황·정정 또는 분석 요청을 이어서 입력하세요.'),
                uncertainties=[],evidence_ids=[source_id]+(['facts'] if f else [])+(['incident'] if i else []),
                information_requests=information_requests or [],dispatch_orders=dispatch_orders or [],
                report_ids=[],basis_version=session['version'],assumptions='')
