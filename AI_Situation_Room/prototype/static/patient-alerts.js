'use strict';
let patientData=null,patientSession=null,patientDetail=null,patientBusy=false,patientFetching=false,patientSignature='';
let patientSelected=null,patientOrder=[],patientListSignature='',patientWide=false,patientCaller=null;
let patientVersions=new Map(),patientRevisions=new Set();
const patientNoticeKey='haeon:patient-notice:v1';
let patientNotices={};
try{const saved=JSON.parse(sessionStorage.getItem(patientNoticeKey)||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))patientNotices=saved;}catch{}
function noticeState(){
 if(!sid)return {known:[],pending:[]};
 const n=patientNotices[sid];
 if(!n||!Array.isArray(n.known)||!Array.isArray(n.pending))patientNotices[sid]={known:[],pending:[],initialized:false};
 return patientNotices[sid];
}
function savePatientNotices(){
 const keys=Object.keys(patientNotices);while(keys.length>20){const key=keys.shift();if(key!==sid)delete patientNotices[key];}
 try{sessionStorage.setItem(patientNoticeKey,JSON.stringify(patientNotices));}catch{}
}
function ingestPatientNotices(d){
 if(!sid||d.session_id!==sid||!d.linked)return;
 const n=noticeState(),known=new Set(n.known),pending=new Set(n.pending);
 for(const item of allAlertItems(d)){if(!known.has(item.id)&&(n.initialized||!item.seen_at))pending.add(item.id);known.add(item.id);}
 const active=new Set(allAlertItems(d).map(i=>i.id));
 n.known=Array.from(known).slice(-5000);n.pending=Array.from(pending).filter(id=>active.has(id)).slice(-5000);
 if(d.last_success_at)n.initialized=true;savePatientNotices();
}
function noticePatientClick(ids){
 const n=noticeState();n.pending=n.pending.filter(id=>!ids.has(id));savePatientNotices();
}
const patientChanged=p=>!!(p.last_event_id&&p.last_event_id!==p.based_on_event_id);
const patientDate=v=>v?new Date(typeof v==='number'?v*1000:v).toLocaleString('ko-KR'):'확인 전';
const patientUrgency=p=>p.status!=='OK'?'분석 상태 확인 필요':p.urgency==='IMMEDIATE'?'즉시 확인 · IMMEDIATE':p.urgency==='WITHIN_30'?'30분 이내 분류 · WITHIN_30':'분류 확인 필요 · '+(p.urgency||'미기록');
const patientName=i=>i.person_name||'환자 '+i.original.person_id.slice(0,8);
const patientJson=v=>v==null?'미기록':typeof v==='string'?v:JSON.stringify(v,null,2);
function closePatient(){patientDetail=null;patientSelected=null;patientSignature='';$('#patientPanel').close();(patientCaller||$('#notifyLink')).focus();}
$('#patientClose').onclick=closePatient;
$('#patientPanel').addEventListener('close',()=>{(patientCaller||$('#notifyLink')).focus();});
$('#patientPanel').addEventListener('cancel',()=>{patientDetail=null;patientSignature='';});
$('#patientBack').onclick=()=>{patientDetail=null;patientSelected=null;patientSignature='';renderPatientAlerts();$('#patientSearch').focus();};
$('#patientMcp').onclick=()=>{closePatient();openInbox('link-one');};
function placePatientPanel(){
 const panel=$('#patientPanel');panel.classList.toggle('patient-wide',patientWide);
 panel.style.left='auto';panel.style.top=window.innerWidth<=700?'12px':'100px';
}
window.addEventListener('resize',()=>{if($('#patientPanel').open)placePatientPanel();});
async function openPatient(caller){
 if(monitor)return;
 if(patientSession!==sid)resetPatientAlerts();
 const received=new Set(noticeState().pending);patientCaller=caller;
 try{
  if(!$('#patientPanel').open){patientDetail=null;patientSelected=null;patientOrder=[];patientVersions=new Map();patientRevisions=new Set();patientSignature='';$('#patientPanel').show();}
  placePatientPanel();renderPatientAlerts();$('#patientTitle').focus();
  noticePatientClick(received);renderPatientAlerts();
 }catch{ $('#patientError').textContent='알림 패널을 열지 못했습니다. 다시 눌러 주세요.';return; }
 await refreshPatientAlerts();
}
$('#notifyLink').onclick=()=>openPatient($('#notifyLink'));
$('#patientOverviewOpen').onclick=()=>openPatient($('#patientOverviewOpen'));
$('#patientExpand').onclick=()=>{patientWide=!patientWide;$('#patientExpand').setAttribute('aria-pressed',String(patientWide));$('#patientExpand').textContent=patientWide?'기본 너비':'넓게 보기';placePatientPanel();};
$('#patientFilter').onchange=()=>{patientListSignature='';renderPatientAlerts();};
$('#alertType').onchange=()=>{$('#patientFilter').value='all';patientListSignature='';renderPatientAlerts();};
$('#patientSearch').oninput=()=>{patientListSignature='';renderPatientAlerts();};
$('#patientReorder').onclick=()=>{patientOrder=[];patientRevisions.clear();patientListSignature='';renderPatientAlerts();};
$('#patientPanel').addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();closePatient();}});
function resetPatientAlerts({keepOpen=false}={}){
 patientSession=sid;patientData=null;patientDetail=null;patientSelected=null;patientSignature='';patientListSignature='';patientOrder=[];
 patientVersions=new Map();patientRevisions=new Set();
 alertSort={key:'time',direction:-1};$('#alertType').value='all';
 $('#patientSearch').value='';$('#patientFilter').value='all';$('#patientError').textContent='';
 if(!keepOpen&&$('#patientPanel').open)closePatient();renderPatientAlerts();
}
function renderPatientOverview(d,same){
 $('#patientSummary').hidden=!sid;$('#patientOverviewOpen').hidden=monitor;
 $('#patientSummaryCase').textContent=snapshot?.session?.id===sid?snapshot.session.title:'현재 해온 사건';
 if(!same||!d.linked||!d.last_success_at){
  $('#patientSummaryCounts').textContent=!same?'환자 알림 확인 중':!d.linked?'Link-One 미연결':'첫 수신 대기';
 }else{
  const immediate=d.items.filter(i=>i.original.status==='OK'&&i.original.urgency==='IMMEDIATE').length;
  const within=d.items.filter(i=>i.original.status==='OK'&&i.original.urgency==='WITHIN_30').length;
  const vessel=d.vessel;
  $('#patientSummaryCounts').textContent=`환자 최신 판정 ${d.items.length}명 · 즉시 확인 ${immediate} · 30분 분류 ${within} · 기타/분석 확인 ${d.items.length-immediate-within} | 선체경사 경고 기록 ${vessel?.last_success_at?`${vessel.items.length}건`:'확인 전'} | 미열람 ${alertUnread(d)}`;
 }
 const transfers=same&&d.linked?patientTransferCodes.map(code=>d.items.filter(i=>patientTransfers(i.original).includes(code)).length):[0,0,0];
 $('#patientTransferSummary').hidden=!transfers.some(Boolean);
 $('#patientTransferSummary').textContent=`링크온 AI 이송 권고 · 헬기 ${transfers[0]}명 · 의료기관 ${transfers[1]}명 · 함정 ${transfers[2]}명`;
 $('#patientSummaryStatus').textContent=same&&d.linked?`링크온 AI 참고 판정 · 마지막 확인 ${patientDate(d.last_success_at)}${d.status==='error'?' · 연결 실패, 이전 수신본 표시':''}${d.missing_count?` · 이전 ${d.missing_count}명 결과 확인 필요`:''}`:'현재 해온 사건 기준 · 수신만으로 AI 검토를 실행하지 않습니다.';
 if(same&&d.linked)$('#patientSummaryStatus').textContent+=` · 선체경사 확인 ${patientDate(d.vessel?.last_success_at)}${d.vessel?.status==='error'?' · 경고 수신 실패, 이전 기록 유지':''}${d.vessel?.truncated?' · 최근 100건만 표시':''}${d.vessel?.missing_count?` · 이전 경고 ${d.vessel.missing_count}건 현재 조회에서 누락`:''}`;
 $('#patientPanelCounts').textContent=$('#patientSummaryCounts').textContent;
}
function renderPatientList(d){
 const target=$('#patientList'),filter=$('#patientFilter').value||'all',query=$('#patientSearch').value.trim().toLowerCase();
 const items=allAlertItems(d),type=$('#alertType').value||'all';renderAlertSort();
 const existing=patientVersions.size>0;
 for(const item of items){const id=alertIdentity(item);if(existing&&patientVersions.get(id)!==item.id)patientRevisions.add(item.id);patientVersions.set(id,item.id);}
 const rows=sortAlertItems(items).filter(i=>
  (type==='all'||type==='vessel'&&isVessel(i)||type==='patient'&&!isVessel(i))&&
  (filter==='all'||filter==='unread'&&!i.seen_at||filter==='IMMEDIATE'&&i.original.status==='OK'&&i.original.urgency==='IMMEDIATE'||filter==='changed'&&patientChanged(i.original)||!isVessel(i)&&(filter==='transfer'&&patientTransfers(i.original).length>0||patientTransferCodes.includes(filter)&&patientTransfers(i.original).includes(filter))||isVessel(i)&&(['LEVEL','RAPID','STALE'].includes(filter)&&i.original.kind===filter||filter==='source_unacked'&&!i.original.ack_count))&&
  [alertName(i),alertIdentity(i),alertSituation(i),alertSummary(i)].join(' ').toLowerCase().includes(query));
 $('#alertResultCount').textContent=`표시 ${rows.length} / 전체 ${items.length}건 · 시간은 환자 분석 완료 / 선박 경고 발생 기준`;
 const signature=JSON.stringify([rows,patientDetail,filter,query,type,alertSort,Array.from(patientRevisions)]);if(signature===patientListSignature)return;patientListSignature=signature;
 const scroll=target.scrollTop,focused=typeof document!=='undefined'?document.activeElement?.dataset?.person:null;
 target.innerHTML=rows.length?rows.map(i=>{const active=patientSelected&&alertIdentity(i)===alertIdentity(patientSelected);return `<button class="patient-row ${active?'selected':''}" data-patient="${esc(i.id)}" data-person="${esc(alertIdentity(i))}" aria-pressed="${!!active}"><span><strong>${esc(alertName(i))}</strong><small>${isVessel(i)?'선박 · 경고 '+esc(i.original.id):'환자 · '+esc(i.original.person_id.slice(0,8))} · ${i.seen_at?'읽음':'미열람'}${active&&i.id!==patientDetail?' · 열람 후 변경':patientRevisions.has(i.id)?' · 새 알림 도착':''}</small></span><span class="patient-urgency">${esc(alertSituation(i))}${patientChanged(i.original)?'<small>판정 후 기록 변경</small>':''}</span><span class="patient-summary">${!isVessel(i)&&patientTransfers(i.original).length?`<span class="transfer-badges">${patientTransferBadges(i.original)}</span><small>링크온 AI 권고</small>`:''}${esc(isVessel(i)?alertSummary(i):i.original.summary||'요약 없음')}</span><span class="patient-row-time"><small>${isVessel(i)?'발생':'분석'} ${esc(patientDate(alertTime(i)))}</small><small>${isVessel(i)?'측정':'기준'} ${esc(patientDate(isVessel(i)?i.original.measured_at:i.original.based_on_at))}</small><small>${isVessel(i)?'출처 확인 기록 '+esc(i.original.ack_count||0)+'건':'위치·관리 확인 불가'}</small></span></button>`;}).join(''):'<p class="patient-empty">'+(items.length?'조건에 맞는 알림이 없습니다.':d.last_success_at?'수신된 알림이 없습니다. 정상 상태를 의미하지 않습니다.':'첫 수신을 기다리고 있습니다.')+'</p>';
 target.querySelectorAll('[data-patient]').forEach(b=>b.onclick=()=>openPatientDetail(b.dataset.patient));target.scrollTop=scroll;
 if(focused){const button=Array.from(target.querySelectorAll('[data-patient]')).find(b=>b.dataset.person===focused);(button||$('#patientTitle')).focus();}
}
async function openPatientDetail(id){
 if(monitor)return;
 const item=allAlertItems(patientData).find(i=>i.id===id);if(!item)return;
 const target=sid;patientDetail=id;patientSelected=JSON.parse(JSON.stringify(item));patientSignature='';renderPatientAlerts();
 $('#patientBody').focus();
 try{await api('/api/sessions/'+target+(isVessel(item)?'/vessel-alert-seen':'/patient-alert-seen'),{alert_id:id});if(target===sid)await refreshPatientAlerts();}
 catch(e){if(target===sid)$('#patientError').textContent=e.message;}
}
function renderPatientAlerts(){
 const d=patientData,button=$('#notifyLink'),same=d&&d.session_id===sid;
 if(same&&patientSelected&&!isVessel(patientSelected)&&d.ended_person_ids?.includes(patientSelected.original.person_id)){
  patientDetail=null;patientSelected=null;patientSignature='';patientListSignature='';
 }
 const unread=alertUnread(d),error=d?.status==='error'||d?.vessel?.status==='error';
 button.querySelector('.inbox-count').textContent=!same?'확인 전':!d.linked?'미연결':error?'! '+unread:d.last_success_at?unread:'확인 전';
 const attention=!!(sid&&noticeState().pending.length);
 button.classList.toggle('has-new-patients',attention);$('#patientNew').hidden=!attention;
 button.setAttribute('aria-label',(!same?'Link-One 중요 알림 확인 전':!d.linked?'Link-One 중요 알림 미연결':`Link-One 중요 알림 미확인 ${unread}건${error?' · 연결 확인 필요':''}`)+(attention?' · 새 알림':''));
 renderPatientOverview(d,same);
 if(same&&d.ended_count)$('#patientSummaryStatus').textContent+=` · 관리 종결 ${d.ended_count}명 제외`;
 if(!$('#patientPanel').open)return;
 const mcp=inboxState.reports.filter(r=>r.project==='link-one'&&r.session_id===sid&&['pending','deferred'].includes(r.status)).length;
 $('#patientMcp').textContent=`외부 보고(MCP) · ${mcp}건`;
 $('#patientTitle').textContent='중요 알림 · 환자 / 선박';$('#patientPanel').classList.toggle('has-patient-detail',!!patientDetail);
 $('#patientBack').hidden=!patientDetail;
 const current=snapshot?.session?.id===sid?snapshot.session.title:'사건 확인 중';
 $('#patientConnection').textContent=!same?'환자 알림 확인 중':!d.linked?'현재 사건은 Link-One DB에 연결되지 않았습니다.':`${current} · 기본 3초 확인 · 마지막 성공 ${patientDate(d.last_success_at)}${d.status==='error'?' · 연결 실패, 재시도 대기':d.status==='waiting'?' · 첫 확인 대기':''}`;
 if(same&&d.linked)renderPatientList(d);else{$('#patientList').innerHTML='<p class="patient-empty">'+(!same?'현재 사건의 알림을 확인하고 있습니다.':'링크온 동기화에서 사건을 연결하면 환자 판정이 표시됩니다.')+'</p>';patientListSignature='';}
 const selected=allAlertItems(d).find(x=>x.id===patientDetail),replacement=patientSelected&&allAlertItems(d).find(x=>alertIdentity(x)===alertIdentity(patientSelected));
 const versionHTML=patientDetail&&!selected?'<p class="error-text">'+(replacement?'새 판정 도착':'이번 조회에서 확인되지 않음')+' · 보고 있는 원문을 유지합니다.</p>'+(replacement?'<button id="patientLatest" class="quiet">최신 판정 보기</button>':''):'';
 if($('#patientVersion').innerHTML!==versionHTML)$('#patientVersion').innerHTML=versionHTML;
 if(patientDetail&&!selected&&replacement)$('#patientLatest').onclick=()=>openPatientDetail(replacement.id);
 if($('#patientReview'))$('#patientReview').disabled=patientBusy||!selected;
 const signature=JSON.stringify([sid,patientDetail,same,d?.linked]);
 if(signature===patientSignature)return;patientSignature=signature;
 if(!same||!d.linked){$('#patientBody').innerHTML=`<p class="patient-empty">${!same?'현재 사건의 환자 알림을 확인하고 있습니다.':'링크온 동기화에서 사건을 연결하면 이곳에 환자 판정이 표시됩니다.'}</p>`;return;}
 const item=patientSelected;
 if(isVessel(item)){$('#patientBody').innerHTML=vesselDetailHTML(item);return;}
 if(item){
  const p=item.original,changed=p.last_event_id&&p.last_event_id!==p.based_on_event_id;
  $('#patientBody').innerHTML=`<article class="patient-detail"><div class="patient-heading"><h3>${esc(patientName(item))}</h3><span class="patient-urgency">${esc(patientUrgency(p))}</span></div>
   ${p.status!=='OK'?'<p class="error-text">링크온의 최신 분석이 성공하지 않았습니다. 이전 결과를 현재 판정으로 사용하지 마세요.</p>':''}
   ${changed?'<p class="error-text">판정 기준과 현재 상태 기록이 다릅니다. 링크온 재분석 여부를 확인하세요.</p>':''}
   ${patientAdviceHTML(p)}
   <p class="inbox-original">${esc(p.summary||'요약 없음')}</p>
   <dl class="inbox-meta"><dt>판정 기준</dt><dd>${esc(patientDate(p.based_on_at))}</dd><dt>분석 완료</dt><dd>${esc(patientDate(p.finished_at))}</dd><dt>해온 수신</dt><dd>${esc(patientDate(item.received_at))}</dd><dt>분석 ID</dt><dd>${esc(p.id)}</dd></dl>
   <details open><summary>권고 이유 · 현장 기록 · 적용 기준</summary>${patientReasonsHTML(p.reasons)}</details>
   <details><summary>분류 · 부족 정보 · 원본 코드</summary><h4>결과</h4><pre>${esc(patientJson(p.outcomes))}</pre><h4>pre-KTAS 참고 판정</h4><pre>${esc(patientJson(p.pre_ktas))}</pre><h4>부족 정보</h4><pre>${esc(patientJson(p.missing))}</pre></details>
   <p class="modal-note">판정 시각과 현재 상황의 차이를 확인하세요. 이 인용은 사실 확정이 아닙니다.</p>
   <button id="patientReview" class="primary" ${patientBusy||!selected?'disabled':''}>해온에 인용하여 검토</button></article>`;
  $('#patientReview').onclick=async()=>{
   if(monitor||patientBusy||!patientData?.items.some(i=>i.id===item.id))return;
   const target=sid;patientBusy=true;patientSignature='';renderPatientAlerts();
   try{if(await send({patientAlert:item})){if(target===sid)closePatient();}}
   finally{patientBusy=false;patientSignature='';if(target===sid)renderPatientAlerts();}
  };
 }else{
  $('#patientBody').innerHTML='<p class="patient-empty">목록에서 환자를 누르면 원문과 판정 시점을 확인할 수 있습니다. 목록 표시와 버튼 클릭은 일괄 읽음으로 처리하지 않습니다.</p>';
 }
}
async function refreshPatientAlerts(){
 // Loading the first session completes an open request; it is not a user switch.
 if(patientSession!==sid)resetPatientAlerts({keepOpen:patientSession===null});
 if(!config||patientFetching||!sid)return;
 patientFetching=true;const target=sid;
 try{
  const result=await api('/api/sessions/'+target+'/patient-alerts');if(target!==sid)return;
  if(result.session_id!==target)return;
  patientData=result;ingestPatientNotices(result);$('#patientError').textContent=[result.error,result.vessel?.error].filter(Boolean).join(' · ');renderPatientAlerts();
 }catch(e){if(target===sid){$('#patientError').textContent='해온 알림 조회 실패 · 마지막 표시 유지';$('#notifyLink').querySelector('.inbox-count').textContent='연결 확인';$('#patientSummaryStatus').textContent='해온 알림 조회 실패 · 마지막 표시 유지';}}
 finally{patientFetching=false;}
}
setInterval(refreshPatientAlerts,1000);
refreshPatientAlerts();
