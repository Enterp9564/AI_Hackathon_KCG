'use strict';
let currentRoster=null;
function currentSituationView(data){
 const live=data.live_situation,room=data.session?.linkone?.room_id;
 const same=!!room&&live?.room_id===room&&live?.session_id===data.session.id;
 const usable=!!(same&&live.summary&&!live.superseded&&live.status!=='disabled');
 const label=!same?'':live.status==='disabled'?'자동 갱신 꺼짐 · 분석용 저장 자료':live.superseded?'새 분석 수신본 기준 · 현재 상태 확인 대기':!live.summary?'분석용 저장 자료 · 현재 상태 첫 확인 대기':live.stale?'갱신 지연 · 마지막 정상 현재 상태':'링크온 현재 상태 · 3초 확인';
 return {usable,summary:usable?live.summary:null,label,live:same?live:null};
}
function currentBasisLabel(l,run){
 const base=l.basis_matches===false?`새 현장 정보 · 분석 저장 자료는 수신본 ${l.basis_revision||'—'} 기준`:l.basis_matches===true?'최신 분석 수신본과 표시 항목 일치':'분석 자료와 최신 상태 일치 여부 미확인';
 return base+(run?.linkone_snapshot_id&&run.linkone_snapshot_id!==l.basis_snapshot_id?` · 선택한 보고는 이전 수신본(S${run.based_on_version}) 기준`:'');
}
function currentPersonTime(state,records){
 return [state?.updated_at,...records.map(r=>r.server_at)].filter(v=>Number.isFinite(Date.parse(v))).sort((a,b)=>Date.parse(b)-Date.parse(a))[0]||'';
}
function renderCurrentSituation(data){
 if(currentRoster&&currentRoster.sid!==sid&&$('#currentRosterRoot')){linkEpoch++;currentRoster=null;$('#linkoneDialog').close();}
 const note=$('#currentSituationNote');if(!note)return;
 const v=currentSituationView(data),l=v.live;
 note.hidden=!data.session.linkone;if(!l){note.textContent=v.label;return;}
 const basis=currentBasisLabel(l,currentRun(data));
 note.textContent=`${v.label} · 최근 확인 ${linkDate(l.checked_at)} · ${basis} · 자동 수신은 AI 검토를 실행하지 않습니다.`;
}
function currentRosterRows(data,query,sort){
 const states=new Map((data.person_state||[]).map(s=>[s.person_id,s])),places=new Map((data.closure_place||[]).map(p=>[p.id,p.name]));
 const latest=new Map((data.person||[]).map(p=>[p.id,currentPersonTime(states.get(p.id),(data.recent_records||[]).filter(r=>r.person_id===p.id))]));
 const value=(p,col)=>{const s=states.get(p.id)||{};return [p.name||'',p.cabin||p.duty||'',linkText(s.rescue)+' '+linkText(s.severity),s.location_force||places.get(s.location_place_id)||linkText(s.location_kind),latest.get(p.id)||s.updated_at||''][col];};
 return (data.person||[]).filter(p=>[p.name,p.cabin,p.duty,p.id].join(' ').toLowerCase().includes(query.toLowerCase())).sort((a,b)=>String(value(a,sort.column)).localeCompare(String(value(b,sort.column)),'ko',{numeric:true})*sort.direction||a.id.localeCompare(b.id));
}
function paintCurrentRoster(){
 const view=currentRoster,d=view?.data;if(!d||!$('#currentRosterRows'))return;
 const wrap=$('#currentRosterWrap'),scroll=wrap.scrollTop;
 const opened=new Set([...wrap.querySelectorAll('details[open]')].map(n=>n.dataset.person));
 const states=new Map((d.person_state||[]).map(s=>[s.person_id,s])),places=new Map((d.closure_place||[]).map(p=>[p.id,p.name]));
 const rows=currentRosterRows(d,$('#currentRosterSearch').value,view.sort);
 $('#currentRosterCount').textContent=`검색 ${rows.length}명 · 명부 포함 ${d.summary?.total??'미확보'}명 · 구조 ${d.summary?.rescued??'—'}명`;
 $('#currentRosterRows').innerHTML=rows.map(p=>{
  const s=states.get(p.id)||{},records=(d.recent_records||[]).filter(r=>r.person_id===p.id),omitted=(d.record_totals?.[p.id]||0)-records.length;
  return `<tr><td><b>${esc(p.name||'미상')}</b><small>${esc(linkRosterExcluded(p))}</small></td><td>${esc(p.cabin||p.duty||'—')}</td><td>${esc(s.rescue?linkText(s.rescue):'미기록')}<small>${esc(s.severity?linkText(s.severity):'미확인')} · ${esc(s.management==='ENDED'?'관리 종결':s.management==='MANAGED'?'관리 중':linkText(s.management))}</small></td><td>${esc(s.location_force||places.get(s.location_place_id)||linkText(s.location_kind)||'미확인')}</td><td>${esc(linkDate(currentPersonTime(s,records)))}<details data-person="${esc(p.id)}" ${opened.has(p.id)?'open':''}><summary>현장기록 ${d.record_totals?.[p.id]||0}건</summary>${records.map(r=>`<article class="current-record"><b>${r.payload.via==='VOICE'?'음성 현장기록':'현장기록'}${r.canceled?' · 취소 참조 있음 (원본 확인)':''}</b><small>${esc(linkDate(r.server_at))} · 이력 ${esc(r.id)}</small><p>${r.canceled?'<del>':''}${esc(r.payload.text||'내용 없음')}${r.canceled?'</del>':''}</p></article>`).join('')||'<p>저장된 현장기록 없음</p>'}${omitted>0?`<p>이전 ${omitted}건 생략 · 분석 수신본에서 확인</p>`:''}</details></td></tr>`;
 }).join('')||'<tr><td colspan="5">표시할 승선원이 없습니다.</td></tr>';
 wrap.scrollTop=scroll;
 $('#currentRosterRoot').querySelectorAll('[data-current-sort]').forEach(b=>{const active=Number(b.dataset.currentSort)===view.sort.column;b.closest('th').setAttribute('aria-sort',active?(view.sort.direction===1?'ascending':'descending'):'none');b.textContent=b.dataset.label+' '+(active?(view.sort.direction===1?'▲':'▼'):'↕');});
}
async function refreshCurrentRoster(){
 const view=currentRoster;
 if(!view||view.pending||view.epoch!==linkEpoch||view.sid!==sid||!$('#currentRosterRoot')||!$('#linkoneDialog').open)return;
 view.pending=true;
 try{
  const d=await api(`/api/sessions/${view.sid}/linkone-current`);
  if(currentRoster!==view||view.epoch!==linkEpoch||sid!==view.sid||!$('#currentRosterRoot'))return;
  const label=d.status==='disabled'?'자동 갱신 꺼짐':d.superseded?'새 분석 수신본이 있습니다 · 현재 상태 다음 확인 대기':d.stale||d.status==='error'?'갱신 지연 · 마지막 정상 자료':d.status==='waiting'?'첫 확인 대기':'현재 상태 · 3초마다 확인';
  $('#currentRosterStamp').textContent=`${label} · 마지막 확인 ${linkDate(d.checked_at)} · 현장 보고이며 사실 확정·AI 검토 완료를 뜻하지 않습니다.`;
  if(d.superseded||d.status==='disabled'){view.data=null;$('#currentRosterRows').innerHTML='<tr><td colspan="5">분석 수신본·변경 내역에서 저장 자료를 확인하세요.</td></tr>';return;}
  if(!view.data||view.data.fingerprint!==d.fingerprint){view.data=d;paintCurrentRoster();}else view.data=d;
 }catch(e){if(currentRoster===view&&view.epoch===linkEpoch&&$('#currentRosterStamp'))$('#currentRosterStamp').textContent='화면 갱신 지연 · 마지막 자료 유지 · '+e.message;}
 finally{view.pending=false;}
}
async function openCurrentRoster(target){
 currentRoster={sid:target,epoch:++linkEpoch,data:null,pending:false,sort:{column:4,direction:-1}};
 linkDialog('승선원 · 현재 상태',`<section id="currentRosterRoot"><div class="linkone-tabs"><button class="primary" type="button">현재 상태 · 자동 갱신</button><button id="openAnalysisSnapshot" type="button">분석 수신본 · 변경 내역</button></div><p id="currentRosterStamp" role="status">현재 상태를 확인하고 있습니다.</p><label for="currentRosterSearch">승선원 검색</label><input id="currentRosterSearch" type="search" placeholder="이름 · 객실 · ID"><p id="currentRosterCount"></p><div id="currentRosterWrap" class="linkone-table-wrap"><table class="incident-table"><thead><tr>${['이름','객실·직책','구조·중증도','현재 위치','최근 기록·상태 시각'].map((label,i)=>`<th scope="col"><button type="button" class="quiet" data-current-sort="${i}" data-label="${label}">${label} ↕</button></th>`).join('')}</tr></thead><tbody id="currentRosterRows"></tbody></table></div></section>`);
 $('#openAnalysisSnapshot').onclick=()=>openLinkDetails(target);
 $('#currentRosterSearch').oninput=paintCurrentRoster;
 $('#currentRosterRoot').querySelectorAll('[data-current-sort]').forEach(b=>b.onclick=()=>{const column=Number(b.dataset.currentSort),sort=currentRoster.sort;currentRoster.sort={column,direction:sort.column===column?-sort.direction:1};paintCurrentRoster();});
 await refreshCurrentRoster();
}
setInterval(refreshCurrentRoster,1000);
