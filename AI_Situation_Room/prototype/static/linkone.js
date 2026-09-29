'use strict';
const linkLabels={room:'사건',person:'승선원',person_state:'현재 상태',person_event:'현장 이력',transfer:'인계',transport_order:'이송 지시',no_accept:'인수 불가',hull_tilt:'선체 경사',room_closure:'종결·재개',roster_upload:'명부 업로드',closure_place:'종결지'};
const linkValue={UNRESCUED:'미구조',RESCUED_ON_SHIP:'구조 · 선내',RESCUED_OFF_SHIP:'구조 · 선외',SHIP:'사고선박',FORCE:'구조세력',CLOSURE:'종결지',IN_TRANSIT:'이송 중',UNKNOWN:'미확인',URGENT:'긴급',EMERGENT:'응급',NON_URGENT:'비응급',DELAYED:'지연',HOLD:'보류',PASSENGER:'승객',CREW:'선원',MALE:'남',FEMALE:'여',ACTIVE:'진행',CLOSED:'종결',NONE:'없음'};
const linkFields={name:'이름',age:'나이',rescue:'구조 상태',severity:'중증도',location_kind:'위치 구분',location_force:'관리 세력',location_place_id:'종결지',management:'관리 상태',transit:'이송 상태',last_event_id:'최종 이력 ID',updated_at:'수정 시각',status:'진행 상태',roll:'좌우 경사',trim:'앞뒤 경사',closed_at:'종결 시각',close_reason:'종결 사유',roster_version:'명부 차수'};
const linkText=v=>v==null?'—':linkValue[v]||String(v);
const linkDate=v=>v?new Date(typeof v==='number'?v*1000:v).toLocaleString('ko-KR'):'아직 수신하지 않음';
let linkEpoch=0,linkSignature='';
function linkDialog(title,html){$('#linkoneTitle').textContent=title;$('#linkoneBody').innerHTML=html;if(!$('#linkoneDialog').open)$('#linkoneDialog').showModal();}
$('#closeLinkone').onclick=()=>{linkEpoch++;$('#linkoneDialog').close();};
$('#linkoneDialog').addEventListener('cancel',()=>linkEpoch++);
$('#linkoneConnect').onclick=async()=>{
 const epoch=++linkEpoch;
 linkDialog('링크온 상황 불러오기','<p role="status">링크온에서 현재 상황 목록을 조회하고 있습니다.</p>');
 try{
  const rooms=await api('/api/linkone/rooms');if(epoch!==linkEpoch)return;
  linkDialog('링크온 상황 불러오기',`<p class="modal-note">사건을 선택하면 전용 해온 세션에 DB 자료를 수신하고 분석을 시작합니다. 같은 사건은 기존 세션을 이어갑니다.</p><label for="linkoneMode">분석 방식</label><select id="linkoneMode"><option value="live" ${config.live_available?'':'disabled'}>LIVE · 실제 AI 분석${config.live_available?'':' (API 설정 필요)'}</option><option value="demo" ${config.live_available?'':'selected'}>DEMO · 규칙 기반 시연</option></select><p class="modal-note">두 방식 모두 실제 링크온 DB를 읽습니다. 동기화 버튼으로 수동 갱신합니다.</p><div id="linkoneError" role="alert"></div><div class="linkone-rooms">${rooms.map(r=>`<button class="linkone-room" data-room-id="${esc(r.id)}"><span class="badge">${r.mode==='REAL'?'실상황':'훈련'} · ${esc(linkText(r.status))}</span><strong>${esc(r.name)}</strong><small>${esc(r.case_no||'사건번호 없음')}</small><span>수신 후 분석 시작 →</span></button>`).join('')||'<p>조회 가능한 사건이 없습니다.</p>'}</div>`);
  $('#linkoneBody').querySelectorAll('[data-room-id]').forEach(b=>b.onclick=async()=>{
   const buttons=[...$('#linkoneBody').querySelectorAll('button')];buttons.forEach(x=>x.disabled=true);
   try{const s=await api('/api/linkone/connect',{room_id:b.dataset.roomId,mode:$('#linkoneMode').value});if(epoch!==linkEpoch)return;$('#linkoneDialog').close();await selectSession(s.id);await refresh();toast('링크온 자료 수신을 시작했습니다. 완료 후 분석합니다.');}
   catch(e){if(epoch===linkEpoch)$('#linkoneError').textContent=e.message;}
   finally{buttons.forEach(x=>x.disabled=false);}
  });
 }catch(e){if(epoch===linkEpoch)linkDialog('링크온 연결 확인',`<p role="alert">${esc(e.message)}</p><p>등록된 SSH 키, 서버 연결 및 로컬 접속 준비 상태를 확인한 뒤 다시 열어주세요.</p>`);}
};
function renderLinkone(data){
 const s=data.session,l=s.linkone,box=$('#linkoneStatus');box.hidden=!l;
 $('#editFacts').hidden=!!l;
 $('.scope-note').textContent=l?'링크온 DB 수신본 기준 · 수동 갱신. 해온의 분석·권고는 원본을 변경하지 않습니다.':'사건 정보는 사용자 입력 기준입니다. 현장 센서·실제 자원 시스템 미연동.';
 if(!l){linkSignature='';$('#send').disabled=sending;return;}
 const running=data.runs.some(r=>['queued','running'].includes(r.status)),busy=l.status==='receiving';
 if(busy)setExecutionStatus({label:'링크온 동기화 중',phase:'DB 수신 · 원본 검증',detail:'검증된 전체 수신본을 저장한 뒤 AI 분석을 시작합니다.',tone:'active'});
 $('#send').disabled=busy||sending;
 const signature=JSON.stringify([s.id,l,running]);if(signature===linkSignature)return;linkSignature=signature;
 const delta=l.delta||{},sum=l.summary||{};
 const status=busy?'DB 자료 수신 중':l.error?'수신 확인 필요':running?'수신 완료 · 분석 중':l.unchanged?'확인 완료 · 변경 없음':'수신 완료';
 box.innerHTML=`<div class="linkone-heading"><div><span class="eyebrow">LINK-ONE → HAEON</span><h2>${status}</h2><p>현재 수신본 ${l.revision||0} · 실제 DB / 읽기 전용 · 수동 동기화</p></div><div class="linkone-actions"><button id="linkoneRefresh" class="primary" ${busy||running?'disabled':''}>링크온 동기화 ↻</button><button id="linkoneDetails" ${l.snapshot_id?'':'disabled'}>승선원 · 변경 내역</button><button id="linkoneAnalyze" class="quiet" ${busy||running||!l.snapshot_id?'disabled':''}>현재 자료 재분석</button></div></div><p class="linkone-stamp">자료 수신 ${esc(linkDate(l.last_received_at))} · 최근 확인 ${esc(linkDate(l.last_checked_at))}</p>${busy?'<p role="status">원본 표를 연속으로 읽고 검증하고 있습니다. 짧은 간격으로 다시 요청하면 최대 5초 대기합니다. 기존 수신본은 보존됩니다.</p>':''}${l.error?`<p class="error-text" role="alert">${esc(l.error)}</p>`:''}${l.snapshot_id?`<div class="linkone-delta"><span>${l.revision===1?'최초 수신':`직전 대비 추가 ${delta.added_count||0} · 변경 ${delta.changed_count||0} · 제거 ${delta.removed_count||0}행`}</span><span>상태 미기록 ${sum.unrecorded||0}명</span><span>선내 위치 기록 ${sum.on_ship||0}명</span></div><p class="modal-note">${l.unchanged?'이번 확인에는 변경이 없어 분석을 반복하지 않았습니다. 표시된 차이는 현재 수신본이 저장될 때의 비교입니다. ':''}미기록자는 미구조 집계에 포함되며 위치는 미확인입니다.</p>`:''}`;
 $('#linkoneRefresh').onclick=()=>linkAction('linkone-sync','자료를 다시 수신하고 있습니다.');
 $('#linkoneAnalyze').onclick=()=>linkAction('linkone-analyze','현재 수신본 재분석을 접수했습니다.');
 $('#linkoneDetails').onclick=()=>openLinkDetails(s.id);

}
async function linkAction(action,message){const target=sid;try{await api(`/api/sessions/${target}/${action}`,{});await refresh();toast(message);}catch(e){toast(e.message);}}
async function openLinkDetails(target,oid){
 const epoch=++linkEpoch;linkDialog('링크온 수신 자료','<p role="status">저장된 자료를 여는 중입니다.</p>');
 try{
  const [snap,history]=await Promise.all([api(`/api/sessions/${target}/linkone${oid?'/'+oid:''}`),api(`/api/sessions/${target}/linkone-history`)]);
  if(epoch!==linkEpoch)return;
  const d=snap.data,states=new Map(d.person_state.map(s=>[s.person_id,s])),places=new Map(d.closure_place.map(p=>[p.id,p.name]));
  linkDialog(`링크온 · ${d.room[0].name}`,`<div class="linkone-detail-head"><label>수신 이력<select id="linkoneHistory">${[...history].reverse().map(h=>`<option value="${esc(h.id)}" ${h.id===snap.id?'selected':''}>수신본 ${h.revision} · ${esc(linkDate(h.received_at))}</option>`).join('')}</select></label><span class="badge">${snap.revision===history.at(-1)?.revision?'현재 수신본':'과거 수신본'}</span></div><p class="modal-note">원본 표의 선택 필드를 저장했습니다. 상태 미기록·제외 사유는 구분합니다. 부상 부위는 그림의 표시 좌표로 계산하며 좌우는 환자 기준입니다. 경계·겹침은 확인이 필요합니다. 기존 수신본에 좌표가 없으면 다음 동기화에서 보강됩니다.</p><div class="linkone-tabs" role="group" aria-label="자료 보기"><button data-link-tab="roster" class="active">승선원 ${d.person.length}</button><button data-link-tab="diff">변경 내역</button><button data-link-tab="other">현장 정보 · 원본</button></div><section id="linkoneRoster"><label for="linkoneSearch">승선원 검색</label><input id="linkoneSearch" type="search" placeholder="이름 · 객실 · ID"><p id="linkoneResult" class="modal-note"></p><div class="linkone-table-wrap"><table class="incident-table"><thead><tr><th>승선원</th><th>구분·객실</th><th>구조·중증도</th><th>현재 위치</th><th>부상 부위·이력</th><th>명부 반영</th></tr></thead><tbody id="linkonePeople"></tbody></table></div></section><section id="linkoneDiff" hidden>${Object.entries(snap.diff.tables).filter(([,v])=>Object.values(v).some(a=>a.length)).map(([table,v])=>`<details class="linkone-change"><summary>${esc(linkLabels[table])} · 추가 ${v.added.length} / 변경 ${v.changed.length} / 제거 ${v.removed.length}</summary>${v.changed.map(c=>`<article><b>${esc(d.person.find(p=>p.id===c.id)?.name||c.id)}</b><ul>${Object.entries(c.fields).map(([f,change])=>`<li>${esc(linkFields[f]||f)}: <del>${esc(linkTextValue(change.before))}</del> → <strong>${esc(linkTextValue(change.after))}</strong></li>`).join('')}</ul></article>`).join('')}${['added','removed'].map(kind=>v[kind].length?`<details><summary>${kind==='added'?'추가':'제거'} 원본 ${v[kind].length}행</summary><pre>${esc(JSON.stringify(v[kind],null,2))}</pre></details>`:'').join('')}</details>`).join('')||'<p>직전 대비 변경이 없습니다.</p>'}</section><section id="linkoneOther" hidden><h3>수신 원본 · 표별 열람</h3><p class="modal-note">이송 지시·인수 불가·경사·종결 이력의 시각을 함께 확인하세요. 이력의 과거 행을 현재 상태로 해석하지 마세요.</p>${Object.entries(d).map(([t,rows])=>`<details><summary>${esc(linkLabels[t])} · ${rows.length}행</summary><pre>${esc(JSON.stringify(rows,null,2))}</pre></details>`).join('')}<details><summary>수신 검증 정보</summary><pre>${esc(JSON.stringify({room_id:snap.room_id,hash:snap.hash,revisions:snap.revisions},null,2))}</pre></details></section>`);
  $('#linkoneHistory').onchange=e=>openLinkDetails(target,e.target.value);
  $('#linkoneBody').querySelectorAll('[data-link-tab]').forEach(b=>b.onclick=()=>{for(const [k,id] of [['roster','Roster'],['diff','Diff'],['other','Other']])$('#linkone'+id).hidden=b.dataset.linkTab!==k;$('#linkoneBody').querySelectorAll('[data-link-tab]').forEach(x=>x.classList.toggle('active',x===b));});
  function people(){const query=$('#linkoneSearch').value.trim().toLowerCase(),rows=d.person.filter(p=>[p.name,p.cabin,p.id,p.duty].join(' ').toLowerCase().includes(query));$('#linkoneResult').textContent=`검색 ${rows.length}명 / 원본 ${d.person.length}명 · 집계 포함 ${snap.summary.total??'미확보'}명`;
   $('#linkonePeople').innerHTML=rows.map(p=>{const s=states.get(p.id),excluded=p.merged_into_id?'병합':p.roster_excluded_at?'명부 제외':p.not_boarded_at?'미탑승':p.removed_at?'제거':'포함';return `<tr><td><b>${esc(p.name||'미상')}</b><small>${esc(p.age??'—')}세 · ${esc(linkText(p.gender))}</small></td><td>${esc(linkText(p.kind))}<small>${esc(p.cabin||p.duty||'—')}</small></td><td>${s?esc(linkText(s.rescue)):'미기록'}<small>${s?esc(linkText(s.severity)):'중증도 미확인'}</small></td><td>${s?esc(s.location_force||places.get(s.location_place_id)||linkText(s.location_kind)):'미확인'}</td><td>${linkInjuries(snap.body_locations?.people?.[p.id])}</td><td>${excluded}${p.off_roster?' · 명부 외':''}</td></tr>`;}).join('')||'<tr><td colspan="6">검색 결과가 없습니다.</td></tr>';}
  $('#linkoneSearch').oninput=people;people();
 }catch(e){if(epoch===linkEpoch)linkDialog('자료 열람 실패',`<p role="alert">${esc(e.message)}</p>`);}
}
function linkTextValue(v){return typeof v==='object'&&v!==null?JSON.stringify(v):linkText(v);}

function linkInjuries(detail){
 if(!detail)return '<span class="muted">부위 기록 없음</span>';
 const location=i=>[...new Set((i.locations||[]).map(x=>x.label))].join(', ')||(i.status==='template_uncertain'?'그림 기준 확인 필요':'부위 미표시·미수신');
 const current=detail.current.map(i=>`<div><b>${esc(i.chip)}</b><small>${esc(location(i))}</small></div>`).join('');
 const history=detail.history.map(i=>`<li>${esc(linkDate(i.server_at))} · ${esc(i.chip)} ${i.type==='CHIP_OFF'?'해제':'표시'}${i.canceled?' · 취소된 기록':''}<small>${esc(location(i))} · 이력 ${esc(i.event_id)}</small></li>`).join('');
 return (current||`<span class="muted">${detail.state_available?'현재 부상 표시 없음':'현재 상태 미기록'}</span>`)+(history?`<details><summary>부위 이력 ${detail.history.length}건${detail.history_omitted?` · 이전 ${detail.history_omitted}건 생략`:''}</summary><ul>${history}</ul></details>`:'');
}
