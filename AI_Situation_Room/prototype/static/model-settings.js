'use strict';
async function openModelSettings(){
 showModal('설정 · AI 및 매뉴얼 검색', '<p id="llmLoading">현재 모델 설정을 확인하고 있습니다.</p>');
 const loading=$('#llmLoading');
 let saved,search;
 try{[saved,search]=await Promise.all([api('/api/settings/llm'),api('/api/settings/manual-search')]);}catch(e){if(loading.isConnected)loading.textContent=e.message;return;}
 if(!loading.isConnected||!$('#modal').open)return;
 showModal('설정 · AI 및 매뉴얼 검색', `<section class="report-section" aria-labelledby="manualSearchTitle">
 <h3 id="manualSearchTitle">매뉴얼 벡터 검색</h3>
 <label style="display:flex;align-items:center;gap:12px"><input id="manualSearchToggle" type="checkbox" role="switch" style="width:auto" aria-describedby="manualSearchHelp manualSearchStatus">국제 SAR 매뉴얼 검색 사용</label>
 <p id="manualSearchHelp" class="modal-note">켜면 사건에 맞는 매뉴얼을 검색해 AI 요원에게 제공합니다. 꺼도 기본 매뉴얼과 사건 기록은 사용합니다. 이 서버의 모든 세션에서 다음 분석부터 적용되며, 재시작 후에도 선택이 유지됩니다. 스위치를 바꾸면 즉시 저장되며, 분석 진행·대기 중에는 변경할 수 없습니다.</p>
 <p id="manualSearchStatus" class="modal-note" role="status" aria-live="polite"></p></section>
 <form id="llmForm"><div class="modal-grid">
 <label class="modal-full">AI 연결<select id="llmProvider"><option value="openai" ${saved.provider==='openai'?'selected':''} ${saved.openai_available?'':'disabled'}>OpenAI${saved.openai_available?'':' · 서버 API 키 미설정'}</option><option value="local" ${saved.provider==='local'?'selected':''}>로컬 LM Studio</option></select></label>
 <label class="modal-full">LM Studio 서버 주소<input id="llmUrl" value="${esc(saved.base_url)}" maxlength="200" required placeholder="http://127.0.0.1:1234"></label>
 <label class="modal-full">로컬 모델 ID<input id="llmModel" value="${esc(saved.model)}" maxlength="200" required></label></div>
 <p class="modal-note">이 해온 서버의 모든 LIVE 세션에서 다음 지시부터 적용됩니다. DEMO 세션은 규칙 기반으로 유지됩니다. 진행·대기 중인 AI 작업이 있으면 전환할 수 없습니다.</p>
 <p class="modal-note">로컬 모델은 PC 부하를 줄이기 위해 한 번에 하나씩 호출합니다. 기존 역할 지침·매뉴얼 근거를 사용하며, 연결 실패 시 자동으로 OpenAI에 전송하지 않습니다. 기상·링크온 수신 같은 별도 네트워크 기능은 그대로입니다.</p>
 <p class="modal-note">Qwen JSON 응답 호환을 위해 로컬 추론 비활성을 요청합니다. 연결 확인은 서버·모델 목록만 조회합니다.</p>
 <div id="llmStatus" class="modal-note" role="status"></div><div class="modal-actions"><button id="llmTest" type="button">연결 확인</button><button id="llmApply" type="submit" class="primary">설정 적용</button></div></form>`);
 const toggle=$('#manualSearchToggle'),searchStatus=$('#manualSearchStatus');
 const paintSearch=()=>{
  toggle.checked=search.enabled;toggle.disabled=!search.available&&!search.enabled;
  searchStatus.textContent=search.enabled?(search.ready_vector?'켜짐 · 벡터 검색 준비 완료':'켜짐 · 벡터 검색 사용 불가, 키워드 검색 상태'):(search.available?'꺼짐 · 필요할 때 켤 수 있습니다.':'꺼짐 · 서버의 벡터 검색 환경 준비가 필요합니다.');
 };
 paintSearch();
 toggle.onchange=async()=>{
  const enabled=toggle.checked;toggle.disabled=true;searchStatus.textContent='검색 설정 적용 중…';
  try{
   search=await api('/api/settings/manual-search',{enabled});
   config.manual_search=search;
   if(config.capabilities)config.capabilities.vector_search=search.ready_vector;
   paintSearch();toast(search.enabled?'매뉴얼 벡터 검색을 켰습니다.':'매뉴얼 벡터 검색을 껐습니다.');
  }catch(e){paintSearch();searchStatus.textContent=e.message;}
 };
 const form=$('#llmForm'),provider=$('#llmProvider'),url=$('#llmUrl'),model=$('#llmModel'),status=$('#llmStatus'),test=$('#llmTest'),apply=$('#llmApply');
 // When no cloud key exists, select the available local option without applying it.
 if(!saved.openai_available)provider.value='local';
 const fields=()=>({provider:provider.value,base_url:url.value,model:model.value});
 const controls=()=>{const local=provider.value==='local';url.disabled=!local;model.disabled=!local;test.disabled=!local;};
 const busy=value=>{[provider,url,model,test,apply].forEach(e=>e.disabled=value);if(!value)controls();};
 provider.onchange=()=>{controls();status.textContent='';};controls();
 test.onclick=async()=>{const data=fields();busy(true);status.textContent='LM Studio 연결 확인 중…';try{const result=await api('/api/settings/llm/test',data);status.textContent=result.message;}catch(e){status.textContent=e.message;}finally{busy(false);}};
 form.onsubmit=async e=>{e.preventDefault();const data=fields();busy(true);status.textContent='설정 적용 중…';try{const result=await api('/api/settings/llm',data);config.llm=result;config.live_available=result.live_available;status.textContent=(result.provider==='local'?'로컬 LM Studio':'OpenAI')+' 적용 완료 · LIVE 세션의 다음 지시부터 사용합니다.';if(snapshot){snapshot.llm=result;renderSnapshot(snapshot);}toast('AI 모델 연결 설정을 저장했습니다.');}catch(e){status.textContent=e.message;}finally{busy(false);}};
}
