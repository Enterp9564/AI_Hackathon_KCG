'use strict';
const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const monitor = location.pathname === '/monitor';
const roleNames = {commander:'상황실장',intel:'정보요원',sar:'수색구조요원',resource:'자원지원요원',critic:'검증요원'};
const conditionNames={fire:'화재',flooding:'침수·경사',weather:'신고 기상',tow:'예인',pollution:'오염',evacuation:'대피·이송'};
const statuses = {queued:'실행 대기',assigned:'임무 수신',running:'검토 중',completed:'보고 완료',failed:'작업 실패',stale:'이전 상황 기준',interrupted:'실행 중단'};
const time = value => value ? new Date(value*1000).toLocaleTimeString('ko-KR',{hour12:false}) : '—';
let config, manuals=[], sid=null, snapshot=null, runId=null, pinned=null, generation=0, lastSync=0, polling=false, requestKind='analysis';
let sessionSignature='', messageSignature='', runSignature='', contentSignature='', toastTimer, sending=false;
let optimisticPrompt='';
const drafts = new Map(), retries = new Map();
if (monitor) { document.body.classList.add('monitor'); $('#fullscreen').hidden=false; $('#backToRoom').hidden=false; $('.situation').append($('.timeline')); }

async function api(path, data) {
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(), path.endsWith('/weather') ? 22000 : 10000);
  try {
    const response=await fetch(path,{method:data===undefined?'GET':'POST',cache:'no-store',signal:controller.signal,
      headers:{'Content-Type':'application/json','X-Session-Token':config?.token || ''},body:data===undefined?undefined:JSON.stringify(data)});
    const result=await response.json();
    if (!response.ok) throw new Error(result.error || `요청 실패 (${response.status})`);
    return result;
  } catch(e) { if(e.name==='AbortError') throw new Error('응답 시간이 초과되었습니다. 입력은 보존됩니다.'); throw e; }
  finally {clearTimeout(timer);}
}
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,5000);}
function showModal(title,body){$('#modalTitle').textContent=title;$('#modalBody').innerHTML=body;if(!$('#modal').open)$('#modal').showModal();}
function list(items){return `<ul>${items.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;}
function requestItemHTML(item,priority){return `<div class="info-request"><div><b>${esc(item.question)}</b><span class="request-meta">${esc(item.source||'상황실장')} · ${esc(priority[item.priority]||item.priority||'보통')}</span></div><p>${esc(item.reason)}</p></div>`;}
function requestHTML(items,title='추가로 필요한 정보'){if(!items?.length)return '';const priority={high:'높음',medium:'보통',low:'낮음'},primary=items.slice(0,2),additional=items.slice(2);return `<div class="info-requests attention-glow"><div class="request-heading"><h3>${esc(title)}</h3><span class="request-count">핵심 ${primary.length}건${additional.length?` · 전체 ${items.length}건`:''}</span></div><p class="modal-note">판단에 바로 필요한 정보부터 표시합니다. 각 요청에는 이유가 함께 표시됩니다.</p>${primary.map(item=>requestItemHTML(item,priority)).join('')}${additional.length?`<details class="request-more"><summary>추가 확인 ${additional.length}건 펼쳐보기</summary>${additional.map(item=>requestItemHTML(item,priority)).join('')}</details>`:''}</div>`;}
function dispatchOrderHTML(order){return `<div class="dispatch-order"><div><b>${esc(order.asset_name||order.asset_id)}</b><span class="request-meta">${esc(order.class||'세력')} · ${esc(order.priority||'high')}</span></div><p>${esc(order.order)}</p><p class="dispatch-reason">${esc(order.reason)}</p><small>${esc(order.status||'제안·실제 출동 확인 필요')}</small></div>`;}
function dispatchHTML(orders,title='출동 지시안'){if(!orders?.length)return '';const primary=orders.slice(0,2),additional=orders.slice(2);return `<div class="dispatch-orders attention-glow"><div class="dispatch-heading"><h3>${esc(title)}</h3><span class="dispatch-count">핵심 ${primary.length}건${additional.length?` · 전체 후보 ${orders.length}건`:''}</span></div><p class="modal-note">AI가 실제 명령을 전송한 것이 아닙니다. 우선 검토할 1~2개를 먼저 표시하고, 추가 후보는 펼쳐서 확인할 수 있습니다.</p>${primary.map(dispatchOrderHTML).join('')}${additional.length?`<details class="dispatch-more"><summary>추가 검토 후보 ${additional.length}건 펼쳐보기</summary>${additional.map(dispatchOrderHTML).join('')}</details>`:''}</div>`;}
function reportHTML(report,defaultSource='상황실장'){if(!report)return '<p class="muted">아직 보고가 없습니다.</p>';const requests=(report.information_requests||[]).map(item=>({...item,source:item.source||defaultSource}));return `<div class="report-section"><h3>판단 요약</h3><p>${esc(report.summary)}</p></div>${dispatchHTML(report.dispatch_orders)}${requestHTML(requests)}<div class="report-section"><h3>검토 결과</h3>${list(report.findings || [])}</div>${report.timeline?.length?`<div class="report-section"><h3>전체 신고·정정 경과 (접수순 원문)</h3><p class="modal-note">과거 이름·인원은 당시 원문입니다. 현재 값은 최신 명부와 상황판을 따릅니다.</p><ol>${report.timeline.map(e=>`<li>${esc(e.text)}</li>`).join('')}</ol></div>`:''}<div class="report-section"><h3>권고 · 다음 확인</h3><p>${esc(report.recommendation)}</p></div><div class="report-section"><h3>가정 · 미확인사항</h3>${report.assumptions?`<p>${esc(report.assumptions)}</p>`:''}${list(report.uncertainties || [])}</div><div class="report-section"><h3>사용 근거</h3>${list((report.evidence_ids || []).map(id=>id==='facts'?'현재 세션의 사용자 상황':id==='weather'?'현재 세션의 기상 조회':id==='incident'?'현재 신고 상태·명부':id==='basic_manual'?'동해 해상사고 기본 대응 매뉴얼':id==='donghae_assets'?'동해 가용세력 후보 목록':snapshot?.messages.find(m=>m.id===id)?.content || snapshot?.attachments.find(a=>a.id===id)?.name || id))}</div>`;}
function saveDraft(){if(sid)drafts.set(sid,{prompt:$('#prompt').value,assumptions:$('#assumptions').value,kind:requestKind});}
function setKind(kind){requestKind=kind;$('#analysisMode').classList.toggle('active',kind==='analysis');$('#simulationMode').classList.toggle('active',kind==='simulation');$('#assumptionsLabel').hidden=kind!=='simulation';}
function resetView(){messageSignature='';runSignature='';contentSignature='';runId=null;optimisticPrompt='';snapshot=null;$('#executionStatus').hidden=true;$('#executionStatus').innerHTML='';$('#messages').innerHTML='';$('#flow').innerHTML='';$('#timeline').innerHTML='';$('#facts').innerHTML='';$('#weather').innerHTML='';$('#evidence').innerHTML='';$('#events').innerHTML='';}
async function selectSession(id){if(id===sid)return;saveDraft();sid=id;generation++;resetView();const draft=drafts.get(id)||{prompt:'',assumptions:'',kind:'analysis'};$('#prompt').value=draft.prompt;$('#assumptions').value=draft.assumptions;setKind(draft.kind);if(!monitor)localStorage.setItem('situation-room:last-session',id);sessionSignature='';await refresh();}
async function deleteSession(id,title){if(!window.confirm(`“${title}” 세션과 저장된 대화·자료를 삭제할까요?\n삭제 후에는 되돌릴 수 없습니다.`))return;try{await api('/api/sessions/'+id+'/delete',{});if(id===sid){sid=null;generation++;resetView();localStorage.removeItem('situation-room:last-session');}sessionSignature='';await refresh();toast('세션을 삭제했습니다.');}catch(e){toast(e.message);}}

async function refresh(){
 if(polling)return;
 polling=true; const epoch=generation;
 try {
   const sessions=await api('/api/sessions');
   const pin=await api('/api/monitor');pinned=pin.session_id;
   if(monitor && pinned!==sid){sid=pinned;generation++;resetView();}
   if(!monitor && !sid && sessions.length){const saved=localStorage.getItem('situation-room:last-session');sid=sessions.some(s=>s.id===saved)?saved:sessions[0].id;generation++;}
   renderSessions(sessions);
   if(!sid){$('#room').hidden=true;$('#emptyState').hidden=false;lastSync=Date.now();if(monitor){$('#emptyState h2').innerHTML='표시할 세션을<br><em>선택해 주세요.</em>';$('#emptyState p').textContent='담당자 화면에서 세션을 선택하고 “상황판에 고정”을 누르세요.';$('#startSession').hidden=true;}return;}
   const target=sid, g=generation;
   const data=await api('/api/sessions/'+target);
   if(target!==sid || g!==generation)return;
   snapshot=data;lastSync=Date.now();renderSnapshot(data);
 } catch(e){ if(!lastSync)$('#connection').textContent=e.message; }
 finally{polling=false;}
}
function renderSessions(sessions){
 $('#sessionCount').textContent=sessions.length;
 const signature=JSON.stringify(sessions.map(s=>[s.id,s.title,s.mode,s.version,s.updated_at]))+sid+pinned;
 if(signature===sessionSignature)return;sessionSignature=signature;
 $('#sessionList').innerHTML=sessions.map(s=>`<div class="session-row"><button class="session-item ${s.id===sid?'selected':''}" data-session="${esc(s.id)}"><strong>${esc(s.title)}</strong><small>${s.mode==='demo'?'DEMO':'LIVE'} · S${s.version}${pinned===s.id?' · 화면 고정':''}</small></button><button class="session-delete" data-delete-session="${esc(s.id)}" data-title="${esc(s.title)}" aria-label="${esc(s.title)} 세션 삭제">×</button></div>`).join('');
 $('#sessionList').querySelectorAll('[data-session]').forEach(b=>b.onclick=()=>selectSession(b.dataset.session));
 $('#sessionList').querySelectorAll('[data-delete-session]').forEach(b=>b.onclick=e=>{e.stopPropagation();deleteSession(b.dataset.deleteSession,b.dataset.title);});
}
function renderSnapshot(data){
 const s=data.session;$('#emptyState').hidden=true;$('#room').hidden=false;
 $('#sessionTitle').textContent=s.title;$('#sessionMeta').textContent=`SESSION ${s.id.slice(0,8).toUpperCase()} · 상황 S${s.version} · 세션별 기억 저장`;
 $('#modeBadge').textContent=s.mode==='demo'?'DEMO · 규칙 기반 / AI 미호출':'LIVE · 실제 AI 호출';$('#modeBadge').classList.toggle('live',s.mode==='live');
 $('#pinButton').disabled=false;$('#pinButton').textContent=pinned===sid?'✓ 상황판 고정됨':'상황판에 고정';
 $('#footerSession').textContent=`${s.id.slice(0,8).toUpperCase()} / ${data.messages.length} MESSAGES`;
 renderExecutionStatus(data);
 const signature=JSON.stringify([s,data.runs,data.tasks,data.attachments,data.events.length]);
 if(signature!==contentSignature){contentSignature=signature;renderFacts(data);renderFlow(data);renderEvents(data);}
 renderMessages(data);renderRunSelect(data);renderTimeline(data);
}
function renderRunSelect(data){const signature=JSON.stringify(data.runs.map(r=>[r.id,r.status]));if(signature===runSignature)return;runSignature=signature;$('#runSelect').innerHTML='<option value="">최신 실행 보기</option>'+[...data.runs].reverse().map((r,i)=>`<option value="${r.id}">${i===0?'최근':'이전'} · ${r.kind==='simulation'?'가정 비교':'상황 검토'} · ${statuses[r.status]}</option>`).join('');$('#runSelect').value=runId||'';}
function currentRun(data){return (runId&&data.runs.find(r=>r.id===runId)) || [...data.runs].reverse().find(r=>r.status==='running') || data.runs.at(-1);}
function compactText(value,max=170){const text=String(value||'').replace(/\s+/g,' ').trim();return text.length>max?text.slice(0,max-1)+'…':text;}
function progressState(run,tasks){
 if(!run)return null;
 const assigned=run.decision?.tasks?.length||0,completed=tasks.filter(t=>['completed','stale'].includes(t.status)).length,running=tasks.filter(t=>['assigned','running'].includes(t.status)).length,requests=tasks.reduce((sum,t)=>sum+(t.report?.information_requests?.length||0),0);
 if(run.status==='queued')return {label:'지시 수행 중',phase:'임무 라우팅 대기',detail:'지시를 접수했습니다. 상황실장이 범위와 우선순위만 확인해 요원에게 전달합니다.',tone:'active'};
 if(run.status==='failed'||run.status==='interrupted')return {label:'지시 처리 중단',phase:statuses[run.status],detail:run.error||'실행이 완료되지 않았습니다. 새 지시로 다시 검토할 수 있습니다.',tone:'error'};
 if(run.status==='completed'||run.status==='stale')return {label:run.status==='stale'?'재검토 필요':'지시 처리 완료',phase:'최종 보고 준비됨',detail:'요원 보고와 검증을 반영한 최종 판단을 확인하세요.',tone:run.status==='stale'?'warn':'complete'};
 if(!run.decision)return {label:'지시 수행 중',phase:'요청 범위 확인 · 임무 라우팅',detail:'상황실장은 요청의 범위와 우선순위만 짧게 확인하고 전문요원에게 바로 전달합니다.',tone:'active'};
 if(assigned&&!tasks.length)return {label:'지시 수행 중',phase:'임무 분배',detail:`상황실장이 전문요원 ${assigned}명에게 집중 검토 임무를 바로 전달하고 있습니다.`,tone:'active'};
 if(running){const requestNote=requests?` · 추가 확인 ${requests}건 수신`:'';return {label:'지시 수행 중',phase:'요원 병렬 검토',detail:`전문요원 ${running}명이 동시에 검토 중입니다${requestNote}.`,tone:'active'};}
 if(assigned&&completed<assigned)return {label:'지시 수행 중',phase:'요원 보고 수신',detail:`임무 ${completed}/${assigned}건의 보고를 기다리고 있습니다.`,tone:'active'};
 return {label:'지시 수행 중',phase:'상황실장 종합',detail:'요원 보고의 근거와 누락 정보를 확인해 최종 제안을 정리합니다.',tone:'active'};
}
function executionStatusHTML(state){return `<span class="execution-led"></span><div class="execution-copy"><b>${esc(state.label)}</b><span>${esc(state.phase)}</span><small>${esc(state.detail)}</small></div><span class="execution-pulse" aria-hidden="true">◌</span>`;}
function setExecutionStatus(state){const el=$('#executionStatus');if(!el)return;if(!state){el.hidden=true;el.innerHTML='';return;}el.hidden=false;el.className=`execution-status ${state.tone||'active'}`;el.innerHTML=executionStatusHTML(state);}
function renderExecutionStatus(data){const run=currentRun(data),tasks=run?data.tasks.filter(t=>t.run_id===run.id):[];setExecutionStatus(progressState(run,tasks));}
function renderMessages(data){
 const signature=JSON.stringify(data.messages);if(signature===messageSignature)return;messageSignature=signature;
 const box=$('#messages'), nearBottom=box.scrollHeight-box.scrollTop-box.clientHeight<90 || !box.children.length, oldTop=box.scrollTop;
 box.innerHTML=data.messages.length?data.messages.map(m=>`<article class="message ${m.role}"><div class="sender"><span>${m.role==='user'?'사용자':'상황실장'}${m.kind==='simulation'?' / 가정 비교':''}</span><span>${time(m.created_at)}</span></div><div class="bubble">${esc(m.content)}${m.assumptions?`<br><small>가정: ${esc(m.assumptions)}</small>`:''}${m.status==='stale'?'<br><span class="error-text">이전 상황 기준 · 재검토 필요</span>':''}${m.report?`<button data-report="${m.run_id}">근거와 조언 상세 ↗</button>`:''}</div></article>`).join(''):'<div class="chat-empty"><b>무엇을 함께 검토할까요?</b><p>현재 상황을 전달하고 필요한 조사를 지시하세요. 요원들의 작업과 보고가 오른쪽에 연결됩니다.</p><p>LIVE 모드에서는 신고·정정이 출처와 함께 저장됩니다. 가정은 시뮬레이션 모드를 사용하세요.</p></div>';
 box.querySelectorAll('[data-report]').forEach(b=>b.onclick=()=>openFinal(b.dataset.report));
 if(nearBottom){box.scrollTop=box.scrollHeight;$('#newMessages').hidden=true;}else{box.scrollTop=oldTop;$('#newMessages').hidden=false;}
}
function renderFacts(data){
 const s=data.session,f=s.facts;
 const unresolved=f.remaining??(f.total!=null&&f.rescued!=null?f.total-f.rescued:'—');
 $('#facts').innerHTML=`<div class="metric-row"><div class="metric"><strong>${f.total??'—'}</strong><small>신고·정정 총원</small></div><div class="metric"><strong>${f.rescued??'—'}</strong><small>구조 보고</small></div><div class="metric"><strong>${unresolved}</strong><small>${f.remaining!=null?'선내 잔류':'미구조 (집계)'}</small></div></div><div class="fact-detail">위치 <b>${esc(f.location||'입력 대기')}</b><br>좌표 <b>${f.lat??'—'} / ${f.lon??'—'}</b><br>출처 <b>${esc(s.facts_source||'자료 없음')}</b>${f.notes?`<br>메모 <b>${esc(f.notes)}</b>`:''}</div>`;
 const incident=s.incident;
 if(incident){
   $('#facts').innerHTML+=`<div class="incident-preview"><strong>${esc(incident.vessel||'사건 현황')} ${incident.report_time?'· 명시 시각 '+esc(incident.report_time):''}</strong><p>${Object.entries(incident.distribution||{}).filter(([k,v])=>v>0).map(([k,v])=>`${esc(k)} ${v}명`).join(' · ')}</p>${Object.values(incident.roster||{}).map(p=>`<p>${esc(p.role)} <b>${esc(p.name||'이름 미확인')}</b> · ${esc(p.location||'위치 미확인')}</p>`).join('')}<button id="incidentDetails">명부 · 환자 · 변경 이력 ↗</button></div>`;
   $('#incidentDetails').onclick=()=>{
     const rows=Object.values(incident.roster||{}).map(p=>`<tr><td>${esc(p.name||'미확인')}</td><td>${esc(p.role)}</td><td>${esc(p.location)}</td><td>${esc(p.condition)}</td><td>${esc(p.lifejacket)}</td></tr>`).join('');
     const changes=data.events.filter(e=>e.type==='incident_updated');
     showModal('현재 신고 상태 · 명부와 이송',`<p class="modal-note">열람 시점의 사용자 신고·정정 기준 S${s.version}. 독립 실측 자료가 아닙니다. 최신 내용은 닫고 다시 열어 확인하세요.</p><h3>확인된 이름의 승선원</h3><table class="incident-table"><tr><th>이름</th><th>직책</th><th>현재 위치</th><th>상태</th><th>구명조끼</th></tr>${rows}</table><h3>사건 대상자 위치별 집계</h3>${list(Object.entries(incident.distribution||{}).map(([k,v])=>`${k}: ${v}명`))}<h3>환자·인계</h3>${list(Object.values(incident.patients||{}).map(p=>`${p.kind||''} ${p.count??'?'}명 · ${p.location||''} · ${p.status||''}`))}<h3>자원 상태</h3>${list(Object.values(incident.assets||{}).map(a=>`${a.name||''} · 자체 승선 ${a.own_crew??'미확인'}명 · ${a.status||''}`))}<h3>위험·대응 현황</h3>${list(Object.entries(incident.conditions||{}).map(([k,v])=>`${conditionNames[k]||k}: ${v}`))}<h3>신고 반영·정정 이력</h3>${changes.map(e=>`<details><summary>${time(e.created_at)} · ${esc(e.label)}</summary><p>${esc(data.messages.find(m=>m.id===e.source_id)?.content||'원문 없음')}</p><pre>${esc(JSON.stringify(e.patch,null,2))}</pre><details><summary>변경 전 상태</summary><pre>${esc(JSON.stringify(e.before,null,2))}</pre></details></details>`).join('')}`);
   };
 }
 const conflicts=data.attachments.filter(a=>a.summary.total!=null&&f.total!=null&&a.summary.total!==f.total);
 const run=currentRun(data), latestVersionMismatch=run&&run.based_on_version!==s.version;
 let priority='현재 접수된 자료를 기준으로 검토합니다. 미확인 현장 변화는 자동 감지하지 않습니다.';
 if(conflicts.length)priority=`확인 필요 · 사용자 총원 ${f.total}명 ↔ 첨부 명부 ${conflicts.at(-1).summary.total}명. 실제 탑승 명부인지 확인한 뒤 상황을 정정하세요.`;
 else if(latestVersionMismatch)priority=`재검토 필요 · 표시 보고는 S${run.based_on_version} 기준, 현재 상황은 S${s.version}입니다.`;
 else if(run?.status==='failed'||run?.status==='interrupted')priority=run.error||'작업이 완료되지 않았습니다. 새 요청으로 재검토하세요.';
 else if(run?.kind==='simulation')priority='시뮬레이션 · 변경 가정과 현재 사실을 분리합니다. 조건부 비교이며 실제 현장 예측이 아닙니다.';
 $('#priority').textContent=priority;$('#priority').classList.toggle('calm',!conflicts.length&&!latestVersionMismatch&&!['failed','interrupted'].includes(run?.status));
 const w=s.weather;
 $('#weather').innerHTML=w?`<strong>${esc(w.values.wind_speed_10m??'—')}</strong> ${esc(w.units.wind_speed_10m||'m/s')} · 풍속<br>기온 ${esc(w.values.temperature_2m??'—')} ${esc(w.units.temperature_2m||'')}<br>자료 ${esc(w.valid_at)} (${esc(w.timezone)})<br>조회 ${time(w.retrieved_at)}<br><small>${esc(w.type)}<br>${esc(w.marine)}</small>`:'<p>조회한 기상 자료가 없습니다.<br>위도·경도를 입력한 뒤 조회하세요.</p><small>Open-Meteo 수동 조회<br>실측·해상 파고 연동은 미구현</small>';
 $('#attachmentCount').textContent=data.attachments.length;
 const builtIn=manuals.map(m=>`<div class="evidence-row"><button data-manual="${m.id}">▧ ${esc(m.title)} ↗</button><small>기본 상황실 자료 · 모든 세션에서 사용</small></div>`).join('');
 const attachments=data.attachments.length?[...data.attachments].reverse().map(a=>`<div class="evidence-row"><button data-evidence="${a.id}">▧ ${esc(a.name)} ↗</button><small>${a.summary.total!=null?`명부 ${a.summary.total}명 · 구조 표시 ${a.summary.rescued}명`:'세션 전용 텍스트 근거'}<br>${time(a.created_at)} · 사용자 첨부</small></div>`).join(''):'명부 CSV · 지침 TXT/MD를<br>대화창에서 첨부할 수 있습니다.';
 $('#evidence').innerHTML=builtIn+attachments;
 $('#evidence').querySelectorAll('[data-manual]').forEach(b=>{b.onclick=()=>{const m=manuals.find(x=>x.id===b.dataset.manual);showModal(m.title,`<p class="modal-note">기본 자료 · 실제 가용성·현장 지시는 별도 확인 필요</p><div class="report-section"><pre>${esc(m.content)}</pre></div>`);};});
 $('#evidence').querySelectorAll('[data-evidence]').forEach(b=>b.onclick=()=>{const a=snapshot.attachments.find(x=>x.id===b.dataset.evidence);showModal(a.name,`<p class="modal-note">사용자 첨부 · 이 세션에만 사용 · 사실 확정 전</p><div class="report-section"><pre>${esc(a.content)}</pre></div>`);});
}
function statusBadge(status){return `<span class="status ${esc(status||'idle')}">${statuses[status]||'배정 대기'}</span>`;}
function activityState(run,tasks){
 if(!run)return {label:'지시를 접수하고 있습니다.',detail:'상황실장이 요청을 읽고 다음 단계를 준비합니다.'};
 if(run.status==='queued')return {label:'지시 접수 · 임무 라우팅 대기',detail:'입력은 저장됐습니다. 상황실장이 범위와 우선순위만 확인해 요원에게 전달합니다.'};
 if(run.status==='running'&&!run.decision)return {label:'상황실장 · 임무 라우팅 중',detail:'요청의 범위와 우선순위만 짧게 확인한 뒤 전문요원에게 바로 전달합니다.'};
 if(run.status==='running'&&run.decision?.tasks?.length&&!tasks.length)return {label:'상황실장 · 임무 분배 중',detail:`전문요원 ${run.decision.tasks.length}명에게 집중 검토 임무를 전달하고 있습니다.`};
 if(run.status==='running'&&tasks.some(t=>['assigned','running'].includes(t.status)))return {label:'전문요원 병렬 검토 중',detail:'각 요원이 맡은 범위를 동시에 확인하고 상황실장에게 보고합니다.'};
 if(run.status==='running'&&tasks.length)return {label:'상황실장 · 요원 보고 종합 중',detail:'개별 보고의 근거와 충돌을 확인한 뒤 사용자에게 제안합니다.'};
 return {label:'상황실장 · 최종 제안 정리 중',detail:'출동 지시안과 추가로 필요한 정보를 정리합니다.'};
}
function activityHTML(run,tasks){const state=activityState(run,tasks);return `<div class="activity-strip activity-glow"><span class="activity-led"></span><div><b>${esc(state.label)}</b><small>${esc(state.detail)}</small></div><span class="activity-spinner" aria-hidden="true">◌</span></div>`;}
function optimisticHTML(){return `<div class="live-activity command-card activity-glow"><div class="activity-kicker">LIVE / REQUEST RECEIVED</div><div class="card-top"><span class="role-name"><span class="role-icon">◈</span>상황실장</span><span class="status running">라우팅 중</span></div><h3>요청을 짧게 분류해 전문요원에게 전달하고 있습니다</h3><p class="request">사용자 → ${esc(optimisticPrompt)}</p><div class="activity-steps"><span class="active">01 요청 수신</span><span>02 임무 분배</span><span>03 요원 보고 수신</span><span>04 최종 제안</span></div><p class="activity-hint"><span class="activity-led"></span>상황실장은 조정하고, 전문 판단은 각 요원이 수행합니다.</p></div>`;}
function showOptimistic(){if(!optimisticPrompt||!$('#flow'))return;setExecutionStatus({label:'지시 수행 중',phase:'요청 범위 확인 · 임무 라우팅',detail:'상황실장은 범위와 우선순위만 확인하고 전문요원에게 바로 전달합니다.',tone:'active'});$('#flow').innerHTML=optimisticHTML();$('#concurrency').textContent='임무 라우팅 준비';}
/* The compact flow keeps the commander's planning output behind the specialist handoff. */
function renderFlow(data){
 const run=currentRun(data),tasks=run?data.tasks.filter(t=>t.run_id===run.id):[];
 if(!run&&optimisticPrompt){showOptimistic();return;}
 const assignments=Array.isArray(run?.decision?.tasks)?run.decision.tasks:[];
 const active=Boolean(run&&['queued','running'].includes(run.status));
 const assigned=assignments.length;
 const planningQuestions=active&&!assigned?(run?.decision?.questions||[]):[];
 const specialist=['intel','sar','resource'].map(role=>{
   const t=tasks.find(item=>item.role===role),assignment=assignments.find(item=>item.role===role);
   const fallback={intel:'자료·명부·기상 확인',sar:'대응지침·근거 검토',resource:'가용자원·제약 검토'}[role];
   return `<article class="agent-card ${esc(t?.status||'')}"><div class="card-top"><div class="role-name">${roleNames[role]}</div>${t?statusBadge(t.status):`<span class="status">${run?.decision&&!assignment?'이번 요청 배정 없음':assignment?'임무 배정됨':'배정 대기'}</span>`}</div><p class="instruction">${esc(t?.instruction||assignment?.instruction||fallback)}</p><p class="reason">${esc(t?.reason||assignment?.reason||'상황실장의 지시를 기다립니다.')}</p>${t?.report?`<div class="report-preview">↗ ${esc(compactText(t.report.summary,110))}</div>${t.report.information_requests?.length?`<div class="agent-request-count">상황실장에게 추가 정보 ${t.report.information_requests.length}건 요청</div>`:''}`:t?.error?`<div class="report-preview error-text">${esc(t.error)}</div>`:''}${t?`<button data-task="${t.id}">지시 · 보고 상세</button>`:''}<div class="profile">전문 임무${t?.started_at?' · '+time(t.started_at):''}</div></article>`;
 }).join('');
 const critic=tasks.find(t=>t.role==='critic');
 const done=tasks.filter(t=>t.role!=='critic'&&['completed','stale'].includes(t.status)).length;
 const final=run?.final;
 const commandSummary=active&&assigned?`상황실장이 ${assigned}개 전문 임무를 배정했습니다. 전문요원들이 각자 검토하고 필요한 정보를 다시 요청합니다.`:compactText(run?.decision?.summary||'요청 범위만 확인해 전문요원에게 임무를 전달합니다.');
 $('#flow').innerHTML=`<div class="command-card ${active?'activity-glow':''}"><div class="card-top"><span class="role-name"><span class="role-icon">◈</span>상황실장</span>${statusBadge(run?.status)}</div><div class="profile">빠른 라우팅 · 임무 배정 · 최종 종합</div><p class="request">사용자 → ${esc(run?.prompt||'새로운 지시를 기다리고 있습니다.')}</p><p>${esc(commandSummary)}</p>${run?.assumptions?`<p class="condition">변경 가정: ${esc(run.assumptions)}</p>`:''}${planningQuestions.length?requestHTML(planningQuestions,'진행 전 확인이 필요한 정보'):''}</div>${run&&!final?activityHTML(run,tasks):''}<div class="flow-arrow">↓ 임무 지시 · 독립 검토 병렬 실행</div><div class="agents-grid">${specialist}</div><div class="flow-arrow">↑ 개별 보고 수신 ${done} / ${assigned}</div><div class="panel critic-card"><span class="role-name">검증요원</span><span class="critic-text">${esc(compactText(critic?.report?.summary||critic?.error||(critic?'수신 보고의 근거·가정·모순을 점검합니다.':'선행 보고 대기 · 보고가 모이면 검증합니다.'),150))}</span>${critic?`<button data-task="${critic.id}">${statuses[critic.status]}</button>`:'<span class="small-badge">검증 대기</span>'}</div><div class="flow-arrow">↓ 상황실장 종합 → 사용자 최종 보고</div><div class="panel final-card"><div class="card-top"><h3>최종 보고 · 사용자 조언</h3><span class="small-badge">${run?'기준 S'+run.based_on_version:'AWAITING'}</span></div>${final?`<p class="final-summary">${esc(compactText(final.summary,220))}</p><p>${esc(compactText(final.recommendation,260))}</p>${dispatchHTML(final.dispatch_orders)}${requestHTML(final.information_requests)}${run.status==='stale'?'<p class="condition">현재 상황과 버전이 다릅니다. 재검토가 필요합니다.</p>':''}<button data-final="${run.id}">비교 · 근거 · 미확인사항 보기 ↗</button>`:`<p class="muted">${esc(run?.error||'요원들의 보고와 검증이 완료되면, 판단에 필요한 내용을 여기에서 확인합니다.')}</p>`}</div>`;
 if(assignments.length===0&&final){
   $('#flow').innerHTML=`<div class="command-card"><div class="card-top"><span class="role-name">◈ 상황실장 · 직접 반영</span>${statusBadge(run.status)}</div><p class="request">${esc(run.prompt)}</p><p>${esc(compactText(final.summary,220))}</p>${dispatchHTML(final.dispatch_orders)}${requestHTML(final.information_requests,'사용자에게 확인할 정보')}<div class="profile">요원 추가 호출 없음 · 저장 S${run.based_on_version}</div></div><div class="flow-arrow">↓ 원문 기록 → 상황·명부 저장 → 사용자 확인</div><div class="panel final-card"><h3>신고 반영 결과</h3>${list((final.findings||[]).slice(0,5))}${(final.findings||[]).length>5?'<p class="muted">전체 반영 내용은 아래에서 확인하세요.</p>':''}<button data-final="${run.id}">반영 내용과 근거 ↗</button></div>`;
 }
 $('#flow').querySelectorAll('[data-task]').forEach(b=>b.onclick=()=>{const t=snapshot.tasks.find(x=>x.id===b.dataset.task);showModal(roleNames[t.role]+' · 지시와 보고',`<div class="detail-meta">기준 S${t.based_on_version} · 시작 ${time(t.started_at)} · 완료 ${time(t.ended_at)}<br>임무 ${esc(t.id.slice(0,12))} · ${statuses[t.status]}</div><div class="report-section"><h3>상황실장의 임무 지시</h3><p>${esc(t.instruction)}</p><h3>배정 이유</h3><p>${esc(t.reason)}</p></div>${t.error?`<p class="error-text">${esc(t.error)}</p>`:''}${reportHTML(t.report,roleNames[t.role])}`);});
 $('#flow').querySelectorAll('[data-final]').forEach(b=>b.onclick=()=>openFinal(b.dataset.final));
}
function openFinal(id){const run=snapshot.runs.find(r=>r.id===id);if(run)showModal('상황실장 · 최종 보고와 조언',`<div class="detail-meta">${run.mode==='demo'?'DEMO · 실제 AI 미호출':'LIVE · 실제 AI 호출'} / 기준 S${run.based_on_version}<br>사용 보고 ${run.final?.report_ids?.length||0}건 · ${statuses[run.status]}</div>${reportHTML(run.final)}`);}
function renderTimeline(data){
 const run=currentRun(data),tasks=run?data.tasks.filter(t=>t.run_id===run.id&&t.started_at).sort((a,b)=>['intel','sar','resource','critic'].indexOf(a.role)-['intel','sar','resource','critic'].indexOf(b.role)):[];
 const assigned=run?.decision?.tasks?.length||0;
 const running=tasks.filter(t=>t.status==='running').length;
 $('#concurrency').textContent=running?`현재 동시 실행 ${running}건`:assigned&&!tasks.length?`임무 배정 ${assigned}건 · 시작 대기`:`완료 ${tasks.filter(t=>['completed','stale'].includes(t.status)).length}건`;
 if(!tasks.length){$('#timeline').innerHTML=assigned?`<p class="timeline-note">상황실장이 ${assigned}개 임무를 배정했습니다. 요원별 작업이 시작되면 실행 구간이 표시됩니다.</p>`:'<p class="timeline-note">실행이 시작되면 요원별 시작·종료 구간이 기록됩니다.</p>';return;}
 const start=Math.min(...tasks.map(t=>t.started_at)),end=Math.max(...tasks.map(t=>t.ended_at||Date.now()/1000)),span=Math.max(.01,end-start);
 $('#timeline').innerHTML=tasks.map(t=>{const elapsed=(t.ended_at||Date.now()/1000)-t.started_at;return `<div class="timeline-row"><span>${roleNames[t.role]}</span><div class="track"><span class="bar ${t.status}" style="left:${(t.started_at-start)/span*100}%;width:${elapsed/span*100}%"></span></div><span>${elapsed.toFixed(1)}s</span></div>`;}).join('')+`<p class="timeline-note">${run.mode==='demo'?'데모 응답 생성 작업의 실제 실행 구간 · AI 추론 성능 수치가 아닙니다.':'서버 작업 시작–완료 기록 · 모델 응답 대기 시간이 포함됩니다.'}</p>`;
}
function renderEvents(data){$('#events').innerHTML=[...data.events].reverse().slice(0,3).map(e=>`<div class="event"><small>${time(e.created_at)}</small>${esc(e.label)}</div>`).join('')||'<div class="event">새로운 지시와 보고가 여기에 기록됩니다.</div>';}

function createSessionDialog(){showModal('새로운 상황실 세션',`<form id="sessionForm"><label>세션 이름<input id="newTitle" required maxlength="80" placeholder="예: 동해 A호 충돌 훈련" autofocus></label><label style="margin-top:15px">실행 방식<select id="newMode"><option value="live" ${config?.live_available?'selected':'disabled'}>실제 AI ${config?.live_available?'':'(서버 API 키 필요)'}</option><option value="demo" ${config?.live_available?'':'selected'}>데모 · 규칙 기반 응답 / API 비용 없음</option></select></label><p class="modal-note">새 세션은 빈 기억으로 시작합니다. 데모에서도 세션 저장·실제 병렬 작업·기억 분리는 작동합니다. 데모 응답은 규칙 기반입니다.</p><div id="modalError" class="modal-error"></div><div class="modal-actions"><button class="primary" type="submit">세션 만들기 →</button></div></form>`);$('#sessionForm').onsubmit=async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{const s=await api('/api/sessions',{title:$('#newTitle').value,mode:$('#newMode').value});$('#modal').close();await selectSession(s.id);toast('빈 기억의 새 세션을 만들었습니다.');}catch(e){$('#modalError').textContent=e.message;}finally{button.disabled=false;}};}
function editFacts(){if(!snapshot)return;const f=snapshot.session.facts,version=snapshot.session.version,target=sid;showModal('현재 상황 · 사용자 확인 후 반영',`<form id="factsForm"><div class="modal-grid"><label>총원 (명)<input id="factTotal" type="number" min="0" max="100000" step="1" value="${f.total??''}"></label><label>구조 보고 (명)<input id="factRescued" type="number" min="0" max="100000" step="1" value="${f.rescued??''}"></label><label class="modal-full">위치 설명<input id="factLocation" maxlength="2000" value="${esc(f.location||'')}" placeholder="사용자가 확인한 위치"></label><label>위도<input id="factLat" type="number" min="-90" max="90" step="any" value="${f.lat??''}"></label><label>경도<input id="factLon" type="number" min="-180" max="180" step="any" value="${f.lon??''}"></label><label class="modal-full">확인된 상황 메모<textarea id="factNotes" maxlength="2000">${esc(f.notes||'')}</textarea></label></div><p class="modal-note">이 입력은 현재 사건의 사실 기록을 갱신합니다. 가정 비교는 대화창의 시뮬레이션 조언을 사용하세요. 인원 변경 후 기존 보고는 이전 상황 기준으로 표시됩니다.</p><button id="sampleFacts" class="quiet" type="button">가상 훈련 예시 채우기 (5명 / 구조 보고 4명)</button><div id="modalError" class="modal-error"></div><div class="modal-actions"><button class="primary" type="submit">확인한 상황 반영</button></div></form>`);$('#sampleFacts').onclick=()=>{$('#factTotal').value=5;$('#factRescued').value=4;$('#factLocation').value='동해 해상 · 가상 훈련';$('#factLat').value=37.5;$('#factLon').value=129.5;$('#factNotes').value='가상 어선 A호 충돌 신고. 침수 여부 확인 필요.';};$('#factsForm').onsubmit=async e=>{e.preventDefault();const facts={};for(const [key,id] of Object.entries({total:'factTotal',rescued:'factRescued',lat:'factLat',lon:'factLon',location:'factLocation',notes:'factNotes'})){const v=$('#'+id).value.trim();if(v)facts[key]=['total','rescued','lat','lon'].includes(key)?Number(v):v;}try{await api('/api/sessions/'+target+'/facts',{version,facts});$('#modal').close();contentSignature='';await refresh();toast('상황을 반영했습니다. 필요한 임무를 재검토하세요.');}catch(e){$('#modalError').textContent=e.message;}};}
async function send(){if(!sid||sending)return;const prompt=$('#prompt').value.trim(),assumptions=requestKind==='simulation'?$('#assumptions').value.trim():'';if(!prompt)return toast('지시 또는 질문을 입력하세요.');if(requestKind==='simulation'&&!assumptions)return toast('비교할 변경 가정을 입력하세요.');const target=sid,payload={prompt,kind:requestKind,assumptions};const signature=JSON.stringify(payload),previous=retries.get(target);payload.request_id=previous?.signature===signature?previous.id:crypto.randomUUID();retries.set(target,{signature,id:payload.request_id});sending=true;optimisticPrompt=prompt;$('#send').disabled=true;showOptimistic();try{await api('/api/sessions/'+target+'/message',payload);retries.delete(target);if(target===sid&&$('#prompt').value.trim()===prompt){$('#prompt').value='';saveDraft();}else if(drafts.get(target)?.prompt.trim()===prompt)drafts.set(target,{...drafts.get(target),prompt:''});optimisticPrompt='';runId=null;contentSignature='';await refresh();toast('지시를 접수했습니다. 상황실장이 이해하고 검토를 시작했습니다.');}catch(e){optimisticPrompt='';if(snapshot)renderFlow(snapshot);toast(e.message);}finally{sending=false;$('#send').disabled=false;}}

$('#newSession').onclick=createSessionDialog;$('#startSession').onclick=createSessionDialog;$('#closeModal').onclick=()=>$('#modal').close();$('#editFacts').onclick=editFacts;
$('#analysisMode').onclick=()=>setKind('analysis');$('#simulationMode').onclick=()=>setKind('simulation');$('#send').onclick=send;
$('#prompt').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send();}});
$('#prompt').addEventListener('input',saveDraft);$('#assumptions').addEventListener('input',saveDraft);
$('#exampleAnalysis').onclick=()=>{$('#prompt').value='현재 상황과 첨부자료를 검토하고, 필요한 조사와 대응 검토사항을 정리해줘.';setKind('analysis');saveDraft();$('#prompt').focus();};
$('#exampleSimulation').onclick=()=>{$('#prompt').value='현재 조건과 변경 가정을 비교하고, 어떤 선택을 검토해야 할지 조언해줘.';$('#assumptions').value='지원 자원 한 척을 사용할 수 없다고 가정';setKind('simulation');saveDraft();$('#prompt').focus();};
$('#newMessages').onclick=()=>{$('#messages').scrollTop=$('#messages').scrollHeight;$('#newMessages').hidden=true;};
$('#runSelect').onchange=e=>{runId=e.target.value||null;contentSignature='';if(snapshot){renderFlow(snapshot);renderFacts(snapshot);renderTimeline(snapshot);}};
$('#pinButton').onclick=async()=>{try{await api('/api/sessions/'+sid+'/pin',{});await refresh();toast('이 세션을 대형 상황판에 고정했습니다.');}catch(e){toast(e.message);}};
$('#fullscreen').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen().catch(()=>toast('브라우저 전체화면을 사용할 수 없습니다.'));};
$('#attach').onclick=()=>$('#fileInput').click();
$('#fileInput').onchange=async e=>{const file=e.target.files[0],target=sid;if(!file||!target)return;if(file.size>100000){toast('초기 프로토타입은 파일당 100KB까지 지원합니다.');e.target.value='';return;}try{await api('/api/sessions/'+target+'/attachments',{name:file.name,content:await file.text()});await refresh();toast('이 세션에 자료를 저장했습니다. 상황실장에게 검토를 요청하세요.');}catch(e){toast(e.message);}finally{e.target.value='';}};
$('#weatherButton').onclick=async()=>{const target=sid;$('#weatherButton').disabled=true;try{await api('/api/sessions/'+target+'/weather',{});await refresh();toast('실제 기상 조회 결과를 저장했습니다.');}catch(e){toast(e.message);}finally{$('#weatherButton').disabled=false;}};
$('#capabilities').onclick=()=>showModal('프로토타입 · 구현 범위',`<div class="report-section"><h3>작동하는 기능</h3>${list(['세션 생성·영속 저장·개별 기억·명부 CSV 검사','실제 서버 병렬 작업·개별 보고·검증·최종 조언','가정 기반 조건 비교·사실 기록 분리','텍스트 근거 검색 · 기상 수동 조회 경로','동해 기본 매뉴얼·가용세력 후보 근거','화재·충돌·침수·오염 위험 시 출동 지시안 제안','대형 모니터 고정 세션 · 입력을 유지하는 상태 갱신'])}<h3>모델 연결</h3><p>실행 방식: LIVE는 실제 AI 호출, DEMO는 규칙 기반 응답.<br>API 키: ${config?.live_available?'서버 설정됨 · 실제 호출 성공 여부는 실행 기록 확인':'미설정 · 현재 데모 체험 가능'}.</p><h3>아직 제공하지 않는 것</h3>${list(['Chroma 벡터 검색·MCP 프로토콜·기상 자동 스케줄','실제 출동 명령 전송·함정 위치·가용성 시스템 연동','물리 시뮬레이션·현장 센서·실제 자원 추적','여러 사용자 인증·세션 삭제/복제·장기 기억 요약','24시간 운영 보증·성능 우위 측정'])}<p class="modal-note">데모 모드의 응답은 규칙 기반입니다. API 실패를 데모 성공으로 바꾸지 않습니다. 실제 AI 사용은 서버 환경변수 OPENAI_API_KEY 설정 후 새 LIVE 세션을 만드세요.</p></div>`);
setInterval(()=>{const age=lastSync?(Date.now()-lastSync)/1000:0;document.body.classList.toggle('connection-lost',age>30);document.body.classList.toggle('connection-delayed',age>10&&age<=30);$('#clock').textContent=new Date().toLocaleTimeString('ko-KR',{hour12:false});if(lastSync)$('#connection').textContent=age>30?`● 연결 끊김 · ${Math.floor(age)}초 전 수신 자료`:age>10?`● 갱신 지연 · ${Math.floor(age)}초`:`● 동기화 정상 · ${new Date(lastSync).toLocaleTimeString('ko-KR',{hour12:false})}`;if(snapshot)renderTimeline(snapshot);},1000);
 (async()=>{try{config=await api('/api/config');manuals=await api('/api/manuals');await refresh();}catch(e){toast('서버 연결 실패: '+e.message);}setInterval(refresh,1000);})();
