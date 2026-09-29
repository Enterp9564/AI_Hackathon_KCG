'use strict';
// The remote application has no verified room handoff yet. Never infer room
// identity from iframe load, and never send credentials through a URL/message.
const linkoneWorkspaceURL='https://114-110-181-118.sslip.io/';
let linkoneWorkspaceFrame=null,linkoneWorkspaceKey=null;

function setWorkspaceView(remote){
  $('#haeonWorkspace').hidden=remote;
  $('#linkoneWorkspace').hidden=!remote;
  for(const [id,selected] of [['haeonWorkspaceButton',!remote],['linkoneWorkspaceButton',remote]]){
    $('#'+id).setAttribute('aria-pressed',String(selected));
    $('#'+id).classList.toggle('active',selected);
  }
}

function resetLinkoneWorkspace(){
  // Keep the remote browsing context alive: destroying it also loses its
  // selected duty/room. HAEON cannot verify the remote room across origins.
  $('#linkoneWorkspaceChanged').hidden=!linkoneWorkspaceFrame;
  $('#linkoneWorkspaceContext').textContent='해온 사건이 바뀌었습니다. 사건 정보를 확인해 주세요.';
  setWorkspaceView(false);
}

function renderLinkoneWorkspace(data){
  const s=data?.session,l=s?.linkone;
  const key=JSON.stringify([s?.id??null,l?.room_id??null]);
  if(linkoneWorkspaceFrame&&linkoneWorkspaceKey!==null&&linkoneWorkspaceKey!==key){
    $('#linkoneWorkspaceChanged').hidden=false;
  }
  linkoneWorkspaceKey=key;
  $('#linkoneWorkspaceContext').textContent=l?.room_id
    ?`해온 연결 사건: ${s.title} · 사건 ID ${l.room_id}`
    :'현재 해온 세션에 연결된 링크온 사건이 없습니다.';
}

function loadLinkoneWorkspace(){
  $('#linkoneFrameHost').replaceChildren();
  const frame=document.createElement('iframe');
  frame.id='linkoneWorkspaceFrame';frame.title='링크온 원본 상황실';
  frame.referrerPolicy='no-referrer';
  frame.setAttribute('sandbox','allow-scripts allow-same-origin allow-forms allow-downloads');
  frame.src=linkoneWorkspaceURL;
  $('#linkoneFrameHost').append(frame);linkoneWorkspaceFrame=frame;
}

$('#linkoneWorkspaceButton').onclick=()=>{
  renderLinkoneWorkspace(snapshot);
  if(!linkoneWorkspaceFrame)loadLinkoneWorkspace();
  setWorkspaceView(true);
};
$('#haeonWorkspaceButton').onclick=()=>setWorkspaceView(false);
$('#linkoneWorkspaceReload').onclick=()=>{
  if(!window.confirm('링크온 화면을 다시 연결할까요? 선택한 근무자·사건 화면이 초기화되거나 재로그인이 필요할 수 있습니다.'))return;
  loadLinkoneWorkspace();
};
setWorkspaceView(false);
