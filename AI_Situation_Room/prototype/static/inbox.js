/* Inbox refresh never calls the engine. send({report}) is the existing chat flow. */
let inboxState={reports:[],links:[]}, inboxProject='link-one', inboxBusy=false, inboxPolling=false, inboxSignature='';
const projectLabels={'link-one':'Link-One','resaid-ai':'RESAID AI'};
const inboxStatus={pending:'검토 대기',deferred:'나중에 검토',sent:'인용 전송됨',rejected:'반영 안 함'};
const inboxActionLabel={received:'수신',seen:'확인',later:'나중에',reject:'반영 안 함',quote_sent:'인용 전송'};
const inboxDate=value=>new Date(typeof value==='number'?value*1000:value).toLocaleString('ko-KR');
function renderInbox(){
  for(const [project,id] of Object.entries({'resaid-ai':'notifyResaid'})){
    const pending=inboxState.reports.filter(r=>r.project===project&&['pending','deferred'].includes(r.status));
    const button=$('#'+id);
    button.querySelector('.inbox-count').textContent=pending.length;
    button.classList.toggle('has-unseen',pending.some(r=>!r.seen_at));
    button.setAttribute('aria-label',`${projectLabels[project]} 미처리 보고 ${pending.length}건`);
  }
  if(!$('#inboxPanel').open)return;
  $('#inboxTitle').textContent=projectLabels[inboxProject]+' 수신함';
  $('#inboxSession').textContent='현재 사건: '+(snapshot?.session.title||'선택한 사건 없음');
  const links=inboxState.links.filter(l=>l.project===inboxProject&&l.session_id===sid);
  $('#inboxLinks').textContent=links.length?'연결된 ID: '+links.map(l=>l.incident_id).join(', '):'현재 사건에 연결된 외부 ID가 없습니다.';
  $('#inboxLinkForm').querySelector('button').disabled=!sid||inboxBusy;
  const reports=inboxState.reports.filter(r=>r.project===inboxProject);
  const signature=JSON.stringify([reports,sid,inboxBusy]);
  if(signature===inboxSignature)return;
  inboxSignature=signature;
  $('#inboxReports').innerHTML=reports.length?reports.map(r=>{
    const p=r.original,active=['pending','deferred'].includes(r.status),same=r.session_id===sid;
    const canSend=active&&same&&!inboxBusy;
    return `<article class="inbox-report ${active?'':'inbox-resolved'}" data-report="${esc(r.id)}">
      <div class="card-heading"><h3>${esc(p.incident_title)}</h3><span class="small-badge">${inboxStatus[r.status]}</span></div>
      <dl class="inbox-meta"><dt>출처</dt><dd>${projectLabels[r.project]}</dd><dt>사건 ID</dt><dd>${esc(p.incident_id)}</dd>
      <dt>보고 시각</dt><dd>${esc(inboxDate(p.reported_at))}</dd><dt>수신 시각</dt><dd>${esc(inboxDate(r.received_at))}</dd></dl>
      <p class="inbox-original">${esc(p.content)}</p>
      ${active?`<p class="inbox-question">이 정보를 인용하여 지시를 전송하시겠습니까?</p>
      ${same?'':`<p class="inbox-mismatch">현재 선택한 사건과 다릅니다.</p><button class="quiet" data-action="switch">연결 사건으로 이동</button>`}
      <div class="inbox-actions"><button class="primary" data-action="quote" ${canSend?'':'disabled'}>인용하여 전송</button>
      <button class="quiet" data-action="later" ${same&&!inboxBusy?'':'disabled'}>나중에</button>
      <button class="quiet" data-action="reject" ${same&&!inboxBusy?'':'disabled'}>반영 안 함</button></div>`:''}
      <details class="inbox-history"><summary>원문·처리 이력</summary><p>보고 ID: ${esc(p.report_id)}</p>
      <ol>${r.history.map(h=>`<li>${esc(inboxDate(h.at))} · ${inboxActionLabel[h.action]||esc(h.action)}</li>`).join('')}</ol>
      ${r.run_id?`<p>지시 ID: ${esc(r.run_id)}</p><p class="modal-note">전송은 접수를 뜻합니다. AI 완료·실패 상태는 연결 사건의 실행 이력에서 확인하세요.</p>`:''}
      ${r.quote?`<pre>${esc(r.quote)}</pre>`:''}</details></article>`;
  }).join(''):'<p class="inbox-empty">아직 수신된 보고가 없습니다.<br>사건 ID를 연결한 뒤 팀 프로젝트 또는 테스트 송신 도구로 보고를 보내세요.</p>';
}
async function refreshInbox(){
  if(!config||monitor||inboxPolling)return;
  inboxPolling=true;
  try{
    inboxState=await api('/api/inbox');
    $('#inboxConnection').textContent=config.capabilities.mcp?'수신 연결 준비됨 · 담당자 승인 후 검토':'MCP 포트 비활성 · 수신함 준비됨';
    renderInbox();
  }catch(e){$('#inboxConnection').textContent='수신함 연결 실패 · 재시도 중';}
  finally{inboxPolling=false;}
}
async function openInbox(project){
  inboxProject=project;inboxSignature='';$('#inboxError').textContent='';
  $('#inboxPanel').showModal();renderInbox();await refreshInbox();
  // Viewing pending reports never approves them. Other incidents stay unread.
  for(const r of inboxState.reports.filter(r=>r.project===project&&r.session_id===sid&&!r.seen_at&&['pending','deferred'].includes(r.status))){
    try{await api('/api/sessions/'+r.session_id+'/inbox-action',{report_id:r.id,action:'seen'});}catch(e){$('#inboxError').textContent=e.message;}
  }
  await refreshInbox();
}
$('#notifyResaid').onclick=()=>openInbox('resaid-ai');
$('#closeInbox').onclick=()=>$('#inboxPanel').close();
$('#inboxLinkForm').onsubmit=async e=>{
  e.preventDefault();if(!sid||inboxBusy)return;
  inboxBusy=true;$('#inboxError').textContent='';renderInbox();
  try{await api('/api/sessions/'+sid+'/inbox-link',{project:inboxProject,incident_id:$('#externalIncident').value.trim()});$('#externalIncident').value='';await refreshInbox();toast('외부 사건 ID를 현재 사건에 연결했습니다.');}
  catch(e){$('#inboxError').textContent=e.message;}
  finally{inboxBusy=false;renderInbox();}
};
$('#inboxReports').onclick=async e=>{
  const button=e.target.closest('button[data-action]');if(!button||inboxBusy)return;
  const report=inboxState.reports.find(r=>r.id===button.closest('[data-report]').dataset.report);
  if(!report)return;
  const action=button.dataset.action;
  $('#inboxError').textContent='';
  if(action==='switch'){
    const sessions=await api('/api/sessions').catch(()=>[]);
    if(!sessions.some(s=>s.id===report.session_id)){$('#inboxError').textContent='연결 사건이 삭제되었습니다. 이 보고는 다시 전송할 수 없습니다.';return;}
    await selectSession(report.session_id);renderInbox();return;
  }
  if(report.session_id!==sid){$('#inboxError').textContent='현재 사건과 보고의 사건이 다릅니다.';return;}
  inboxBusy=true;renderInbox();
  try{
    if(action==='quote'){
      if(await send({report}))$('#inboxPanel').close();
      else $('#inboxError').textContent='전송 결과를 확인하지 못했습니다. 재시도해도 같은 보고는 중복 실행되지 않습니다.';
    }else{
      await api('/api/sessions/'+sid+'/inbox-action',{report_id:report.id,action});
      if(action==='later')$('#inboxPanel').close();
    }
    await refreshInbox();
  }catch(e){$('#inboxError').textContent=e.message;}
  finally{inboxBusy=false;renderInbox();}
};
setInterval(refreshInbox,2000);
refreshInbox();
