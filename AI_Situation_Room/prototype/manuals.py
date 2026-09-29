"""Static operational knowledge used to make the commander proactive.

The catalog is advisory: it never claims a unit is actually available or dispatched.
"""
import json
import re
from pathlib import Path


ROOT = Path(__file__).parent / 'manuals'


def _read_catalog():
    return json.loads((ROOT / 'donghae_assets.json').read_text(encoding='utf-8'))


def asset_catalog():
    return _read_catalog()['units']


def local_catalog_applies(session):
    if not session or not session.get('linkone'):return True
    location=str(session.get('facts',{}).get('location',''))
    # Only explicit local incident locations qualify; an operator's station does not.
    return any(name in location for name in ('묵호','동해시','동해항','울릉','독도')) and not any(name in location for name in ('제주','부산','서귀포'))


def manual_evidence(session=None):
    catalog = _read_catalog()
    items=[
        {'id':'basic_manual','title':'동해 해상사고 기본 대응 매뉴얼',
         'content':(ROOT / 'basic-response-manual.md').read_text(encoding='utf-8')},
        {'id':'donghae_assets','title':'동해 가용세력 후보 목록',
         'content':json.dumps(catalog,ensure_ascii=False), 'summary':{'source':catalog['source']}},
    ]
    if not local_catalog_applies(session):items=[e for e in items if e['id']!='donghae_assets']
    return items


def _unit(asset_id):
    return next(item for item in asset_catalog() if item['asset_id'] == asset_id)


def _order(asset_id, order, reason, priority='high'):
    unit = _unit(asset_id)
    return {'asset_id':asset_id, 'asset_name':unit['name'], 'class':unit['class'],
            'order':order, 'reason':reason, 'priority':priority,
            'status':'제안·실제 출동 확인 필요', 'basis':['basic_manual','donghae_assets']}


def recommended_dispatch(prompt, session):
    """Return conservative order proposals for clear maritime danger keywords."""
    if not local_catalog_applies(session):return []
    incident = session.get('incident') or {}
    text = ' '.join(str(x) for x in [prompt, session.get('facts',{}).get('location',''),
                                     session.get('facts',{}).get('notes',''),
                                     incident.get('vessel',''), json.dumps(incident,ensure_ascii=False)]).lower()
    fire = any(word in text for word in ('화재','불길','연기','폭발'))
    collision = any(word in text for word in ('충돌','파공'))
    flooding = any(word in text for word in ('침수','침몰','기울','표류'))
    pollution = any(word in text for word in ('오염','기름','유출')) or fire or collision or flooding
    if not (fire or collision or flooding or pollution):
        return []
    orders = []
    near_mukho = any(word in text for word in ('묵호','동해','연안')) and not any(word in text for word in ('울릉','독도','광역'))
    if near_mukho:
        orders.append(_order('coastal_rescue_mukho','묵호파출소 연안구조정 출동 지시안',
            '인근 연안구조정이 인명 구조·환자 이송과 현장 상태 확인을 먼저 수행할 후보입니다.'))
        orders.append(_order('306함','306함 출동 지시안',
            '연안~근해 사고의 구조·현장 통제와 화재 대응을 맡을 중형함정 후보입니다.'))
        orders.append(_order('P-60','P-60 초동 확인 출동 지시안','연안 경비 세력으로 사고 위치·표류 방향·승선원 상태를 빠르게 확인할 후보입니다.','medium'))
    elif any(word in text for word in ('울릉','독도','광역')):
        orders.append(_order('3007함','대형함정 출동 지시안','광역·울릉도 인근 사고의 장거리 구조와 지휘 지원을 맡을 후보입니다.'))
        orders.append(_order('coastal_rescue_donghae','연안구조정 출동 지시안','확인 가능한 인근 연안구조정으로 인명 구조를 우선 검토합니다.'))
    else:
        orders.append(_order('coastal_rescue_donghae','인근 파출소 연안구조정 출동 지시안','사고 위치가 특정되지 않아 우선 인근 연안구조정의 출동 가능 여부를 확인합니다.'))
        orders.append(_order('306함','중형함정 출동 지시안','연안~근해 구조와 현장 통제를 위한 후보입니다.'))
    if pollution:
        orders.append(_order('방제3호정','방제3호정 출동 지시안','화재·충돌·침수로 유류 유출 등 2차 해양오염 우려가 있어 초동 방제를 병행 검토합니다.'))
    if flooding or '예인' in text or '기관 정지' in text or '표류' in text:
        orders.append(_order('예인3호정','예인3호정 출동 지시안','기관 정지·침수·표류 상태에서 추가 표류와 침몰 위험을 줄일 예인 후보입니다.','medium'))
    return orders


def normalize_orders(items):
    """Keep only known catalog units and complete model-generated orders."""
    known = {item['asset_id'] for item in asset_catalog()}
    result=[]
    for item in items or []:
        if not isinstance(item,dict) or item.get('asset_id') not in known:
            continue
        unit=_unit(item['asset_id'])
        result.append({'asset_id':unit['asset_id'], 'asset_name':unit['name'], 'class':unit['class'],
                       'order':str(item.get('order') or f"{unit['name']} 출동 지시안"),
                       'reason':str(item.get('reason') or '기본 대응 매뉴얼상 역할 검토가 필요합니다.'),
                       'priority':str(item.get('priority') or 'high'),
                       'status':'제안·실제 출동 확인 필요',
                       'basis':item.get('basis') or ['basic_manual','donghae_assets']})
    dedup=[];seen=set()
    for item in result:
        if item['asset_id'] not in seen:
            seen.add(item['asset_id']);dedup.append(item)
    return dedup
