const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function setup(){
  const nodes=new Map();
  const node=id=>{
    if(!nodes.has(id))nodes.set(id,{open:false,textContent:'',innerHTML:'',hidden:false,style:{},
      classList:{toggle(){}},setAttribute(){},focus(){},addEventListener(){},
      showModal(){this.open=true;},close(){this.open=false;},
      querySelector(){return node(id+' child');},querySelectorAll(){return [];},
      getBoundingClientRect(){return {left:100,bottom:100};}});
    return nodes.get(id);
  };
  const ctx=vm.createContext({$:node,sid:null,snapshot:null,config:null,monitor:false,
    inboxState:{reports:[]},window:{innerWidth:1000,innerHeight:800,addEventListener(){}},
    setInterval(){},esc:String,openInbox(){},send:async()=>true,
    api:async()=>({session_id:ctx.sid,linked:false,items:[],unread:0})});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/patient-alerts.js'),'utf8'),ctx);
  return {ctx,node,run:code=>vm.runInContext(code,ctx)};
}

test('opening during initial load stays open when the first session arrives',async()=>{
  const {ctx,node,run}=setup();
  await node('#notifyLink').onclick();assert.equal(node('#patientPanel').open,true);
  ctx.sid='first-session';ctx.config={};
  await run('refreshPatientAlerts()');
  assert.equal(node('#patientPanel').open,true,'initial session adoption must not close an explicit open request');
  assert.match(node('#patientBody').innerHTML,/링크온 동기화/);
});

test('explicit session switch closes the old patient panel',async()=>{
  const {ctx,node,run}=setup();ctx.sid='one';ctx.config={};
  await node('#notifyLink').onclick();assert.equal(node('#patientPanel').open,true);
  ctx.sid='two';run('resetPatientAlerts()');
  assert.equal(node('#patientPanel').open,false);
});

test('opening is immediate while a patient API response is pending',async()=>{
  const {ctx,node,run}=setup();ctx.sid='one';ctx.config={};
  let resolve;ctx.api=()=>new Promise(done=>{resolve=done;});
  const loading=run('refreshPatientAlerts()');
  await node('#notifyLink').onclick();assert.equal(node('#patientPanel').open,true);
  resolve({session_id:'one',linked:false,items:[],unread:0});await loading;
  assert.equal(node('#patientPanel').open,true);
});
