'use strict';
let patientData=null,patientSession=null,patientDetail=null,patientBusy=false,patientFetching=false,patientSignature='';
const patientDate=v=>v?new Date(typeof v==='number'?v*1000:v).toLocaleString('ko-KR'):'확인 전';
const patientUrgency=p=>p.status!=='OK'?'분석 상태 확인 필요':p.urgency==='IMMEDIATE'?'즉시 확인 · IMMEDIATE':p.urgency==='WITHIN_30'?'30분 이내 분류 · WITHIN_30':'분류 확인 필요 · '+(p.urgency||'미기록');
const patientName=i=>i.person_name||'환자 '+i.original.person_id.slice(0,8);
const patientJson=v=>v==null?'미기록':typeof v==='string'?v:JSON.stringify(v,null,2);
function closePatient(){patientDetail=null;patientSignature='';$('#patientPanel').close();}
$('#patientClose').onclick=closePatient;
$('#patientPanel').addEventListener('close',()=>$('#notifyLink').focus());
$('#patientPanel').addEventListener('cancel',()=>{patientDetail=null;patientSignature='';});
$('#patientBack').onclick=()=>{patientDetail=null;patientSignature='';renderPatientAlerts();};
$('#patientMcp').onclick=()=>{closePatient();openInbox('link-one');};
function placePatientPanel(){
 const panel=$('#patientPanel'),rect=$('#notifyLink').getBoundingClientRect();
 if(window.innerWidth<=600){panel.style.left='12px';panel.style.top='auto';return;}
 panel.style.left=Math.max(12,Math.min(rect.left,window.innerWidth-572))+'px';
 panel.style.top=Math.max(12,Math.min(rect.bottom+10,window.innerHeight-520))+'px';
}
window.addEventListener('resize',()=>{if($('#patientPanel').open)placePatientPanel();});
$('#notifyLink').onclick=async()=>{
 if(patientSession!==sid)resetPatientAlerts();
 patientDetail=null;patientSignature='';$('#patientError').textContent='';
 if(!$('#patientPanel').open)$('#patientPanel').showModal();placePatientPanel();renderPatientAlerts();await refreshPatientAlerts();
};
function resetPatientAlerts({keepOpen=false}={}){
 patientSession=sid;patientData=null;patientDetail=null;patientSignature='';
 if(!keepOpen&&$('#patientPanel').open)closePatient();renderPatientAlerts();
}
function renderPatientAlerts(){
 const d=patientData,button=$('#notifyLink'),same=d&&d.session_id===sid;
 button.querySelector('.inbox-count').textContent=!same?'확인 전':!d.linked?'미연결':d.status==='error'?'! '+d.unread:d.last_success_at?d.unread:'확인 전';
 button.classList.toggle('has-new-patients',!!(same&&d.unread));
 button.setAttribute('aria-label',!same?'Link-One 환자 알림 확인 전':!d.linked?'Link-One 환자 알림 미연결':`Link-One 환자 알림 미확인 ${d.unread}건${d.status==='error'?' · 연결 확인 필요':''}`);
 if(!$('#patientPanel').open)return;
 const mcp=inboxState.reports.filter(r=>r.project==='link-one'&&r.session_id===sid&&['pending','deferred'].includes(r.status)).length;
 $('#patientMcp').textContent=`외부 보고(MCP) · ${mcp}건`;
 $('#patientTitle').textContent=patientDetail?'환자 판정 상세':'환자 알림';
 $('#patientBack').hidden=!patientDetail;
 const current=snapshot?.session?.id===sid?snapshot.session.title:'사건 확인 중';
 $('#patientConnection').textContent=!same?'환자 알림 확인 중':!d.linked?'현재 사건은 Link-One DB에 연결되지 않았습니다.':`${current} · 기본 3초 확인 · 마지막 성공 ${patientDate(d.last_success_at)}${d.status==='error'?' · 연결 실패, 재시도 대기':d.status==='waiting'?' · 첫 확인 대기':''}`;
 const selected=d?.items.find(x=>x.id===patientDetail);
 const signature=patientDetail?JSON.stringify([sid,patientDetail,!!selected,patientBusy]):JSON.stringify([sid,d?.items,d?.missing_count,d?.linked]);
 if(signature===patientSignature)return;patientSignature=signature;
 if(!same||!d.linked){$('#patientBody').innerHTML=`<p class="patient-empty">${!same?'현재 사건의 환자 알림을 확인하고 있습니다.':'링크온 동기화에서 사건을 연결하면 이곳에 환자 판정이 표시됩니다.'}</p>`;return;}
 const item=d.items.find(x=>x.id===patientDetail);
 if(patientDetail&&!item){$('#patientBody').innerHTML='<p role="status">새 판정으로 변경되었거나 이번 조회에서 확인되지 않습니다. 목록에서 현재 자료를 확인하세요.</p>';return;}
 if(item){
  const p=item.original,changed=p.last_event_id&&p.last_event_id!==p.based_on_event_id;
  $('#patientBody').innerHTML=`<article class="patient-detail"><div class="patient-heading"><h3>${esc(patientName(item))}</h3><span class="patient-urgency">${esc(patientUrgency(p))}</span></div>
   ${p.status!=='OK'?'<p class="error-text">링크온의 최신 분석이 성공하지 않았습니다. 이전 결과를 현재 판정으로 사용하지 마세요.</p>':''}
   ${changed?'<p class="error-text">판정 기준과 현재 상태 기록이 다릅니다. 링크온 재분석 여부를 확인하세요.</p>':''}
   <p class="inbox-original">${esc(p.summary||'요약 없음')}</p>
   <dl class="inbox-meta"><dt>판정 기준</dt><dd>${esc(patientDate(p.based_on_at))}</dd><dt>분석 완료</dt><dd>${esc(patientDate(p.finished_at))}</dd><dt>해온 수신</dt><dd>${esc(patientDate(item.received_at))}</dd><dt>분석 ID</dt><dd>${esc(p.id)}</dd></dl>
   <details open><summary>링크온 판정 근거</summary><pre>${esc(patientJson(p.reasons))}</pre></details>
   <details><summary>분류 · 부족 정보 · 원본 코드</summary><h4>결과</h4><pre>${esc(patientJson(p.outcomes))}</pre><h4>pre-KTAS 참고 판정</h4><pre>${esc(patientJson(p.pre_ktas))}</pre><h4>부족 정보</h4><pre>${esc(patientJson(p.missing))}</pre></details>
   <p class="modal-note">판정 시각과 현재 상황의 차이를 확인하세요. 이 인용은 사실 확정이 아닙니다.</p>
   <button id="patientReview" class="primary" ${patientBusy?'disabled':''}>해온에 인용하여 검토</button></article>`;
  $('#patientReview').onclick=async()=>{
   const target=sid;patientBusy=true;patientSignature='';renderPatientAlerts();
   try{if(await send({patientAlert:item})){if(target===sid)closePatient();}}
   finally{patientBusy=false;patientSignature='';if(target===sid)renderPatientAlerts();}
  };
 }else{
  $('#patientBody').innerHTML=(d.items.length?`<p class="modal-note">환자별 최신 판정 ${d.items.length}건 · 미확인 ${d.unread}건</p><div class="patient-list">${d.items.map(i=>`<button class="patient-row" data-patient="${esc(i.id)}"><span class="patient-row-top"><strong>${esc(patientName(i))}</strong><span class="small-badge">${i.seen_at?'읽음':'새 판정'}</span></span><span class="patient-urgency">${esc(patientUrgency(i.original))}</span><span class="patient-summary">${esc(i.original.summary||'요약 없음')}</span><small>${esc(patientDate(i.original.finished_at))} · 상세 보기 →</small></button>`).join('')}</div>`:`<p class="patient-empty">${d.last_success_at?'이 사건에서 수신된 환자 분석 결과가 없습니다. 환자 상태가 정상이라는 뜻은 아닙니다.':'아직 첫 수신을 기다리고 있습니다.'}</p>`)+(d.missing_count?`<p class="modal-note">이전 환자 ${d.missing_count}명의 결과가 이번 조회에서 확인되지 않습니다. 위험 해소로 처리하지 않습니다.</p>`:'');
  $('#patientBody').querySelectorAll('[data-patient]').forEach(b=>b.onclick=async()=>{
   const target=sid;patientDetail=b.dataset.patient;patientSignature='';renderPatientAlerts();
   try{await api('/api/sessions/'+target+'/patient-alert-seen',{alert_id:patientDetail});if(target===sid)await refreshPatientAlerts();}
   catch(e){if(target===sid)$('#patientError').textContent=e.message;}
  });
 }
}
async function refreshPatientAlerts(){
 // Loading the first session completes an open request; it is not a user switch.
 if(patientSession!==sid)resetPatientAlerts({keepOpen:patientSession===null});
 if(!config||monitor||patientFetching||!sid)return;
 patientFetching=true;const target=sid;
 try{
  const result=await api('/api/sessions/'+target+'/patient-alerts');if(target!==sid)return;
  patientData=result;$('#patientError').textContent=result.error||'';renderPatientAlerts();
 }catch(e){if(target===sid){$('#patientError').textContent='해온 알림 조회 실패 · 마지막 표시 유지';$('#notifyLink').querySelector('.inbox-count').textContent='연결 확인';}}
 finally{patientFetching=false;}
}
setInterval(refreshPatientAlerts,1000);
refreshPatientAlerts();
