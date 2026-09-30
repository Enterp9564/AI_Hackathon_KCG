'use strict';
// Patient classifications and source-issued vessel warnings share display only.
let alertSort={key:'time',direction:-1};
const vesselKind={LEVEL:'각도 도달',RAPID:'급변',STALE:'측정 지연'};
const patientOutcomeNames={AIR_TRANSFER:'헬기 이송 필요',HOSPITAL_TRANSFER:'의료기관 이송 필요',VESSEL_TRANSFER:'함정 이송 필요',RECHECK:'환자 상태 재확인 필요',RETRIAGE:'중증도 재분류 검토',MONITOR:'관찰 유지',INSUFFICIENT:'판단 자료 부족'};
const patientTransferCodes=['AIR_TRANSFER','HOSPITAL_TRANSFER','VESSEL_TRANSFER'];
const patientOutcomeCodes=p=>p.status==='OK'&&Array.isArray(p.outcomes)?[...new Set(p.outcomes.filter(x=>typeof x==='string'))]:[];
const patientTransfers=p=>patientTransferCodes.filter(c=>patientOutcomeCodes(p).includes(c));
const patientOutcomeLabels=p=>patientOutcomeCodes(p).map(c=>patientOutcomeNames[c]||'출처 코드 '+c);
const patientTransferBadges=p=>patientTransfers(p).map(c=>`<strong class="transfer-badge">${esc(patientOutcomeNames[c])}</strong>`).join(' ');
function patientAdviceHTML(p){
 const labels=patientOutcomeLabels(p);if(!labels.length)return '';
 return `<section class="patient-advice" aria-label="링크온 AI 권고"><h4>링크온 AI 권고</h4><div class="transfer-badges">${patientTransferBadges(p)}</div><p>${labels.map(esc).join(' · ')}</p><small>출처의 검토 권고입니다. 실제 현장 요청·출동 지시·이송 완료와 구분합니다.</small></section>`;
}
function patientReasonsHTML(reasons){
 if(!Array.isArray(reasons)||!reasons.length)return '<p class="muted">근거 미기록</p>';
 return reasons.map(r=>r&&typeof r==='object'?`<article class="patient-reason"><p><strong>${esc(r.text||'추가 근거')}</strong></p>${r.record?`<p><b>현장 기록 인용</b> · ${esc(patientJson(r.record))}</p>`:''}${r.criterion?`<p><b>링크온 적용 기준</b> · ${esc(patientJson(r.criterion))}</p>`:''}</article>`:`<p>${esc(patientJson(r))}</p>`).join('');
}
const isVessel=i=>i?.category==='vessel';
const allAlertItems=d=>[...(d?.items||[]),...(d?.vessel?.items||[]).map(i=>({...i,category:'vessel'}))];
const alertIdentity=i=>isVessel(i)?'vessel:'+i.original.id:'patient:'+i.original.person_id;
const alertName=i=>isVessel(i)?'선체경사 · '+(i.original.axis==='ROLL'?'좌우':i.original.axis==='TRIM'?'선수·선미':'선박'):patientName(i);
const alertSituation=i=>isVessel(i)?(vesselKind[i.original.kind]||'출처 분류 '+(i.original.kind||'미기록')):patientUrgency(i.original);
const alertSummary=i=>isVessel(i)?[i.original.title,i.original.message].filter(Boolean).join(' · '):[...patientOutcomeLabels(i.original),i.original.summary||'요약 없음'].join(' · ');
const alertTime=i=>isVessel(i)?i.original.raised_at:i.original.finished_at;
const alertUnread=d=>(d?.unread||0)+(d?.vessel?.unread||0);
function sortAlertItems(items){
 const value=i=>alertSort.key==='time'?(Number.isFinite(Date.parse(alertTime(i)))?Date.parse(alertTime(i)):null):
  alertSort.key==='name'?alertName(i):alertSort.key==='situation'?alertSituation(i):alertSummary(i);
 return [...items].sort((a,b)=>{
  const av=value(a),bv=value(b);if(av===null||bv===null){if(av!==bv)return av===null?1:-1;}
  const order=alertSort.key==='time'?(av===null?0:av-bv):av.localeCompare(bv,'ko',{numeric:true});
  return order*alertSort.direction||alertIdentity(a).localeCompare(alertIdentity(b),'ko',{numeric:true})||a.id.localeCompare(b.id);
 });
}
function setAlertSort(key){
 if(!['name','situation','content','time'].includes(key))return;
 alertSort={key,direction:alertSort.key===key?-alertSort.direction:key==='time'?-1:1};
 patientListSignature='';renderPatientAlerts();
}
function renderAlertSort(){
 for(const [key,label] of [['name','이름 / 대상'],['situation','상황'],['content','내용'],['time','시간']]){
  const button=$('#alertSort-'+key),active=key===alertSort.key;
  button.textContent=label+(active?(alertSort.direction===1?' ▲':' ▼'):' ↕');
  button.setAttribute('aria-pressed',String(active));
  button.setAttribute('aria-label',label+' · '+(active?(alertSort.direction===1?'오름차순':'내림차순')+' 정렬 중 · 반대로 정렬':'클릭하여 정렬'));
  button.onclick=()=>setAlertSort(key);
 }
}
function vesselDetailHTML(item){
 const p=item.original;
 const angle=v=>typeof v==='number'?v+'°':'미기록';
 return `<article class="patient-detail"><h3>${esc(alertName(item))}</h3><p class="patient-urgency">${esc(alertSituation(item))} · 링크온 원본 경고</p>
 <p class="inbox-original">${esc(p.title||'제목 없음')}</p><p>${esc(p.message||'추가 내용 없음')}</p>
 <dl class="inbox-meta"><dt>경고 발생</dt><dd>${esc(patientDate(p.raised_at))}</dd><dt>측정 시각</dt><dd>${esc(patientDate(p.measured_at))}</dd><dt>해온 수신</dt><dd>${esc(patientDate(item.received_at))}</dd><dt>좌우 경사 / 트림</dt><dd>${esc(angle(p.roll))} / ${esc(angle(p.trim))}</dd><dt>이전 좌우 / 트림</dt><dd>${esc(angle(p.prev_roll))} / ${esc(angle(p.prev_trim))}</dd><dt>이전 측정</dt><dd>${esc(patientDate(p.prev_measured_at))}</dd><dt>출처 확인 기록</dt><dd>${p.ack_count?`${esc(p.ack_count)}건 · 최근 ${esc(patientDate(p.last_acked_at))}`:'없음'}</dd></dl>
 <details open><summary>출처 근거와 참고</summary><p>${esc(p.basis||'근거 미기록')}</p><p>${esc(p.note||'')}</p><p>${esc(p.standard||'')}</p><small>원본 경고 ID ${esc(p.id)} · 종류 ${esc(p.kind)} · 기준 각도 ${esc(angle(p.level_deg))}</small></details>
 <p class="modal-note">출처 확인은 위험 해소를 뜻하지 않습니다. 해온 열람은 링크온 확인 기록을 변경하지 않습니다. 선체경사 경고는 자동 AI 검토를 실행하지 않습니다.</p></article>`;
}
