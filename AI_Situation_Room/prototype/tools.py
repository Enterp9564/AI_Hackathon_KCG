"""Small, explicit evidence tools. Manual content is labeled advisory and sourced."""
import json
import re
import time
import urllib.parse
import urllib.request


def evidence_for(snapshot, query):
    evidence = []
    session = snapshot['session']
    from .manuals import manual_evidence
    evidence.extend(manual_evidence())
    if session['facts']:
        evidence.append({'id':'facts','title':f"사용자 상황 S{session['version']}",
                         'content':json.dumps(session['facts'],ensure_ascii=False)})
    if session.get('weather'):
        evidence.append({'id':'weather','title':'Open-Meteo 모델 기상 조회',
                         'content':json.dumps(session['weather'],ensure_ascii=False)})
    for m in snapshot.get('messages',[]):
        if m['role']=='user' and m.get('kind')!='simulation':
            evidence.append({'id':m['id'],'title':'미확인 외부 보고 인용' if m.get('external_report_id') else '사용자 신고 원문','content':m['content'], 'external_report_id':m.get('external_report_id'),'reported_at':m['created_at']})
    if session.get('incident'):
        evidence.append({'id':'incident','title':'현재 신고 상태·명부','content':json.dumps(session['incident'],ensure_ascii=False)})
    words = set(re.findall(r'[\w가-힣]{2,}',query.lower()))
    ranked = []
    for attachment in snapshot['attachments']:
        score = sum(word in attachment['content'].lower() for word in words)
        # CSV is always pertinent to a situation review; documents use lexical relevance.
        if attachment['summary'] or score:
            ranked.append((score, attachment))
    for _, a in sorted(ranked,key=lambda item:item[0],reverse=True)[:5]:
        evidence.append({'id':a['id'],'title':a['name'],'content':a['content'][:16000],
                         'summary':a['summary']})
    return evidence


def weather(lat, lon):
    query = urllib.parse.urlencode(dict(latitude=lat,longitude=lon,
        current='temperature_2m,wind_speed_10m,wind_direction_10m',wind_speed_unit='ms',timezone='Asia/Seoul'))
    url='https://api.open-meteo.com/v1/forecast?'+query
    with urllib.request.urlopen(url,timeout=15) as response:
        payload=json.load(response)
    values=payload.get('current')
    if not values or not values.get('time'):
        raise ValueError('현재 시각 자료를 제공받지 못했습니다.')
    return {'source':'Open-Meteo Forecast','source_url':url,'type':'모델 기반 자료 · 현장 실측 아님',
        'requested':{'lat':lat,'lon':lon},'returned':{'lat':payload.get('latitude'),'lon':payload.get('longitude')},
        'valid_at':values['time'],'retrieved_at':time.time(),'timezone':payload.get('timezone'),
        'values':values,'units':payload.get('current_units',{}),'marine':'해상 파고 미연동'}
