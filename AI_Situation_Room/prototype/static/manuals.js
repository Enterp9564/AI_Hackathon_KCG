'use strict';
function safeManualURL(value){try{const u=new URL(value);return u.protocol==='https:'?u.href:'';}catch{return '';}}
function manualSearchLabel(search){
 const labels={ok:'관련 근거 제공',partial:'관련 근거 일부 제공 · 입력 예산으로 부분 검색',no_match:'수록 자료에서 관련 근거 없음',unavailable:'검색 준비 필요',error:'검색 실패',not_requested:'이번 지시는 국제 매뉴얼 검색 미실행'};
 return (labels[search?.status]||'검색 상태 확인 필요')+(search?.warnings?.includes('degraded')?' · 벡터 검색을 사용할 수 없어 키워드 검색으로 대체':'')+(search?.warnings?.includes('context_omitted')?' · 검색 입력 한도로 사건 정보 일부 제외':'');
}
function manualReportHTML(runId,role='commander'){
 const contexts=(snapshot?.manual_contexts||[]).filter(c=>c.run_id===runId&&c.role===role);
 const run=snapshot?.runs.find(r=>r.id===runId);
 if(!contexts.length&&!run?.manual_search)return '';
 return `<section class="report-section manual-reference"><h3>국제 SAR 매뉴얼</h3><p>${esc(manualSearchLabel(run?.manual_search))}</p><p class="modal-note">선별 한국어 초안 14개 · 원문 전체 검토·국내 승인 SOP 아님</p>${contexts.map(c=>`<button type="button" data-manual-context="${esc(c.id)}" data-manual-run="${esc(runId)}">${esc(c.stage==='final'?'최종 종합':roleNames[c.role]||c.role)}에 전달한 근거 ${c.evidence.length}개 보기</button>`).join('')}</section>`;
}
function manualContextHTML(record){
 const status=manualSearchLabel(record.search);
 return `<p class="modal-note">${esc(status)}<br>실행 당시 저장한 한국어 작성 요약입니다. 제공됐다는 사실만으로 보고가 해당 내용을 인용·정확히 적용했음을 뜻하지 않습니다.</p>${record.items.map(item=>{
 const remote=safeManualURL(item.source_url);
 const local='/api/manual-sources/'+encodeURIComponent(item.source_id)+'/pdf?sha256='+encodeURIComponent(item.original_sha256||'')+'#page='+Number(item.pdf_pages[0]);
 return `<section class="report-section manual-reference"><h3>${esc(item.title)}</h3><p>${esc(item.source_title)} · ${esc(item.source_version)}<br>PDF ${esc(item.pdf_pages.join(', '))}쪽 · ${esc(item.locator)}</p><p class="manual-content">${esc(item.content)}</p><h4>적용 제한</h4><ul>${item.limitations.map(s=>`<li>${esc(s)}</li>`).join('')}</ul><p class="modal-note">전문 운용 검토가 필요한 초안 · 공식 번역 아님</p><a href="${esc(local)}" target="_blank" rel="noopener noreferrer">로컬 원본 PDF</a>${remote?` · <a href="${esc(remote)}" target="_blank" rel="noopener noreferrer">공식 출처</a>`:''}</section>`;
 }).join('')}`;
}
document.addEventListener('click',async event=>{
 const button=event.target.closest?.('[data-manual-context]');if(!button)return;
 const target=sid,epoch=generation,run=button.dataset.manualRun,context=button.dataset.manualContext;
 button.disabled=true;
 try{
  const record=await api(`/api/sessions/${encodeURIComponent(target)}/runs/${encodeURIComponent(run)}/manual-contexts/${encodeURIComponent(context)}`);
  if(sid!==target||generation!==epoch)return;
  showModal('국제 SAR · 실행 당시 제공 근거',manualContextHTML(record));
  $('#closeModal').focus();
 }catch(e){if(sid===target&&generation===epoch)toast(e.message);}
 finally{if(button.isConnected)button.disabled=false;}
});
