const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function setup(){
  const nodes=new Map();
  function element(){return {hidden:false,textContent:'',children:[],attributes:{},
    classList:{toggle(){}},setAttribute(k,v){this.attributes[k]=v;},
    append(child){this.children.push(child);},replaceChildren(){this.children=[];},focus(){}};}
  const node=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
  node('#prompt').value='작성 중 지시';
  const ctx=vm.createContext({$:node,document:{createElement:element},window:{confirm:()=>false},
    snapshot:{session:{id:'a',title:'훈련 A',linkone:{room_id:'room-a'}}}});
  const file=path.join(__dirname,'../static/linkone-workspace.js');
  if(fs.existsSync(file))vm.runInContext(fs.readFileSync(file,'utf8'),ctx);
  return {ctx,node,run:code=>vm.runInContext(code,ctx),open(){
    assert.equal(typeof node('#linkoneWorkspaceButton').onclick,'function','링크온 탭 열기 연결 필요');
    node('#linkoneWorkspaceButton').onclick();
  }};
}

test('same-session view switching keeps the frame and unsent draft',()=>{
  const h=setup();assert.equal(h.node('#linkoneFrameHost').children.length,0);
  h.open();const frame=h.node('#linkoneFrameHost').children[0];assert.ok(frame);
  assert.equal(h.node('#haeonWorkspace').hidden,true);
  h.node('#haeonWorkspaceButton').onclick();
  assert.equal(h.node('#haeonWorkspace').hidden,false);
  h.open();assert.equal(h.node('#linkoneFrameHost').children[0],frame);
  assert.equal(h.node('#prompt').value,'작성 중 지시');
});

test('session reset preserves the authenticated frame but returns to HAEON and warns',()=>{
  const h=setup();h.open();const frame=h.node('#linkoneFrameHost').children[0];h.run('resetLinkoneWorkspace()');
  assert.equal(h.node('#linkoneFrameHost').children[0],frame);
  assert.equal(h.node('#linkoneWorkspace').hidden,true);
  assert.equal(h.node('#haeonWorkspace').hidden,false);
  assert.equal(h.node('#linkoneWorkspaceChanged').hidden,false);
  assert.match(h.node('#linkoneWorkspaceContext').textContent,/사건 정보를 확인/);
});

test('linked room is a local reference and is never claimed as verified remote entry',()=>{
  const h=setup();h.open();
  assert.match(h.node('#linkoneWorkspaceContext').textContent,/room-a/);
  const frame=h.node('#linkoneFrameHost').children[0];
  assert.equal(frame.src,'https://114-110-181-118.sslip.io/');
  h.ctx.snapshot={session:{id:'b',title:'훈련 B'}};
  h.run('renderLinkoneWorkspace(snapshot)');
  assert.equal(h.node('#linkoneFrameHost').children[0],frame);
  assert.equal(h.node('#linkoneWorkspaceChanged').hidden,false);
  h.open();assert.match(h.node('#linkoneWorkspaceContext').textContent,/연결된 링크온 사건이 없습니다/);
});

test('canceling reconnect leaves the remote login and view untouched',()=>{
  const h=setup();h.open();const frame=h.node('#linkoneFrameHost').children[0];
  h.node('#linkoneWorkspaceReload').onclick();
  assert.equal(h.node('#linkoneFrameHost').children[0],frame);
  h.ctx.window.confirm=()=>true;
  h.node('#linkoneWorkspaceReload').onclick();
  assert.notEqual(h.node('#linkoneFrameHost').children[0],frame);
});
