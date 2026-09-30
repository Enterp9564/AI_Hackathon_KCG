const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function setup(storage=new Map()){
  const nodes=new Map();
  const node=id=>{
    if(!nodes.has(id))nodes.set(id,{open:false,textContent:'',innerHTML:'',hidden:false,style:{},
      value:'',dataset:{},scrollTop:0,
      classList:{values:new Set(),toggle(k,on){if(on)this.values.add(k);else this.values.delete(k);},contains(k){return this.values.has(k);}},setAttribute(){},focus(){},addEventListener(){},
      show(){this.open=true;},showModal(){this.open=true;},close(){this.open=false;},
      querySelector(){return node(id+' child');},querySelectorAll(){return [];},
      getBoundingClientRect(){return {left:100,bottom:100};}});
    return nodes.get(id);
  };
  const ctx=vm.createContext({$:node,sid:null,snapshot:null,config:null,monitor:false,
    inboxState:{reports:[]},window:{innerWidth:1000,innerHeight:800,addEventListener(){}},
    sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
    setInterval(){},esc:String,openInbox(){},send:async()=>true,
    api:async()=>({session_id:ctx.sid,linked:false,items:[],unread:0})});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/alert-list.js'),'utf8'),ctx);
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

function data(ids=['a']){return {session_id:'one',linked:true,last_success_at:1,unread:ids.length,status:'ok',items:ids.map((id,i)=>({id,seen_at:null,received_at:1,original:{id,person_id:'person-'+i,status:'OK',urgency:'IMMEDIATE',summary:'가상 판정 '+id}}))};}
test('default recent order, column direction toggles, missing dates last',()=>{
 const s=setup(),d=data(['a','b','c']);d.items[0].original.finished_at='2026-09-29T01:00:00Z';d.items[1].original.finished_at='2026-09-29T02:00:00Z';
 s.ctx.sortInput=d.items;s.run('sortInput=sortAlertItems(sortInput)');assert.equal(s.ctx.sortInput[0].id,'b');
 s.run('setAlertSort("time")');s.run('sortInput=sortAlertItems(sortInput)');assert.equal(s.ctx.sortInput[0].id,'a');assert.equal(s.ctx.sortInput[2].id,'c');
 d.items[0].person_name='가나다';d.items[1].person_name='나머지';s.ctx.sortInput=d.items;s.run('setAlertSort("name");sortInput=sortAlertItems(sortInput)');assert.equal(s.ctx.sortInput[0].id,'a');
 s.run('setAlertSort("name");sortInput=sortAlertItems(sortInput)');assert.equal(s.ctx.sortInput.at(-1).id,'a');
});
test('vessel arrivals contribute attention, type filtering and separate seen path',async()=>{
 const s=setup();s.ctx.sid='one';s.ctx.config={};const d=data([]);d.vessel={status:'ready',last_success_at:1,unread:1,items:[{id:'v1',seen_at:null,original:{id:'10',kind:'RAPID',title:'선체 급변',message:'출처 내용',raised_at:'2026-09-29T02:00:00Z',ack_count:0}}]};
 await receive(s,d);assert(s.node('#notifyLink').classList.contains('has-new-patients'));await s.node('#notifyLink').onclick();
 assert.match(s.node('#patientList').innerHTML,/선체/);s.node('#alertType').value='patient';s.run('renderPatientAlerts()');assert.doesNotMatch(s.node('#patientList').innerHTML,/data-patient=/);
 const calls=[];s.ctx.api=async(p,body)=>{calls.push({p,body});return d;};await s.run('openPatientDetail("v1")');assert.match(s.node('#patientBody').innerHTML,/확인은 위험 해소/);assert.doesNotMatch(s.node('#patientBody').innerHTML,/id="patientReview"/);
 const writes=calls.filter(c=>c.body);assert.equal(writes.length,1);assert.match(writes[0].p,/vessel-alert-seen$/);assert.equal(writes[0].body.alert_id,'v1');assert.match(s.node('#patientBody').innerHTML,/출처 내용/);
});
async function receive(s,d){s.ctx.api=async()=>d;await s.run('refreshPatientAlerts()');}
test('transfer recommendations appear in overview, list, filters and source detail',async()=>{
 const s=setup();s.ctx.sid='one';s.ctx.config={};const d=data(['air','both','other']);
 d.items[0].original.outcomes=['AIR_TRANSFER','RECHECK'];d.items[1].original.outcomes=['AIR_TRANSFER','VESSEL_TRANSFER','INSUFFICIENT'];
 d.items[0].original.reasons=[{text:'가상 이송 권고',record:'가상 현장 기록',criterion:'출처 기준 원문'}];
 d.items[2].original.outcomes=['MONITOR'];await receive(s,d);await s.node('#notifyLink').onclick();
 assert.match(s.node('#patientTransferSummary').textContent,/헬기 2명/);
 assert.match(s.node('#patientList').innerHTML,/헬기 이송 필요/);
 s.node('#patientFilter').value='AIR_TRANSFER';s.run('renderPatientAlerts()');assert.equal((s.node('#patientList').innerHTML.match(/data-patient=/g)||[]).length,2);
 s.node('#patientFilter').value='VESSEL_TRANSFER';s.run('renderPatientAlerts()');assert.equal((s.node('#patientList').innerHTML.match(/data-patient=/g)||[]).length,1);
 s.node('#patientFilter').value='transfer';s.node('#patientSearch').value='헬기';s.run('renderPatientAlerts()');assert.equal((s.node('#patientList').innerHTML.match(/data-patient=/g)||[]).length,2);
 await s.run('openPatientDetail("air")');assert.match(s.node('#patientBody').innerHTML,/링크온 AI 권고/);assert.match(s.node('#patientBody').innerHTML,/헬기 이송 필요/);assert.match(s.node('#patientBody').innerHTML,/출처 기준 원문/);assert.match(s.node('#patientBody').innerHTML,/출동 지시/);
});
test('failed analyses cannot advertise current transfer advice; unknown codes stay escaped',()=>{
 const s=setup();s.ctx.p={status:'FAILED',outcomes:['AIR_TRANSFER']};assert.equal(s.run('patientTransfers(p).length'),0);
 s.ctx.p={status:'OK',outcomes:['AIR_TRANSFER','AIR_TRANSFER','NEW_CODE']};assert.equal(s.run('patientTransfers(p).length'),1);
 assert.match(s.run('patientOutcomeLabels(p).join(" ")'),/NEW_CODE/);
});
test('management end removes pending emphasis and the open detail without a write',async()=>{
 const s=setup();s.ctx.sid='one';s.ctx.config={};await receive(s,data());
 await s.run('openPatientDetail("a")');
 const ended={...data([]),ended_count:1,ended_person_ids:['person-0']};
 await receive(s,ended);
 assert.equal(s.node('#notifyLink').classList.contains('has-new-patients'),false);
 assert.equal(s.node('#notifyLink').querySelector('.inbox-count').textContent,0);
 assert.equal(s.run('patientDetail'),null);assert.equal(s.run('patientSelected'),null);
 assert.doesNotMatch(s.node('#patientBody').innerHTML,/id="patientReview"/);
 assert.match(s.node('#patientSummaryStatus').textContent,/관리 종결 1명 제외/);
 await receive(s,data(['reopened']));assert(s.node('#notifyLink').classList.contains('has-new-patients'));
});
test('button click stops attention but preserves unread and never sends a write',async()=>{
 const s=setup();s.ctx.sid='one';s.ctx.config={};await receive(s,data());
 assert(s.node('#notifyLink').classList.contains('has-new-patients'));
 let writes=0;s.ctx.api=async(path,body)=>{if(body)writes++;return data();};
 await s.node('#notifyLink').onclick();
 assert.equal(s.node('#notifyLink').classList.contains('has-new-patients'),false);
 assert.equal(s.node('#notifyLink').querySelector('.inbox-count').textContent,1);assert.equal(writes,0);
 await receive(s,data());assert.equal(s.node('#notifyLink').classList.contains('has-new-patients'),false);
 await receive(s,data(['b']));assert(s.node('#notifyLink').classList.contains('has-new-patients'));
});
test('click during fetch acknowledges only already received versions',async()=>{
 const s=setup();s.ctx.sid='one';s.ctx.config={};await receive(s,data());
 let resolve;s.ctx.api=()=>new Promise(r=>{resolve=r;});const pending=s.run('refreshPatientAlerts()');
 await s.node('#notifyLink').onclick();assert.equal(s.node('#notifyLink').classList.contains('has-new-patients'),false);
 resolve(data(['b']));await pending;assert(s.node('#notifyLink').classList.contains('has-new-patients'));
});
test('noticed versions survive reload, while new versions and other sessions alert',async()=>{
 const storage=new Map(),a=setup(storage);a.ctx.sid='one';a.ctx.config={};await receive(a,data());await a.node('#notifyLink').onclick();
 const b=setup(storage);b.ctx.sid='one';b.ctx.config={};await receive(b,data());assert.equal(b.node('#notifyLink').classList.contains('has-new-patients'),false);
 b.ctx.sid='two';await receive(b,{...data(),session_id:'two'});assert(b.node('#notifyLink').classList.contains('has-new-patients'));
});
test('summary counts latest classifications independently of read count',async()=>{
 const s=setup();s.ctx.sid='one';s.ctx.config={};const d=data(['a','b']);d.unread=0;d.items.forEach(i=>i.seen_at=1);await receive(s,d);
 assert.match(s.node('#patientSummaryCounts').textContent,/최신 판정 2/);
 assert.match(s.node('#patientSummaryCounts').textContent,/즉시 확인 2/);
 assert.match(s.node('#patientSummaryCounts').textContent,/미열람 0/);
});
test('monitor fetches cached summaries but cannot open or mark alerts',async()=>{
 const s=setup();s.ctx.sid='one';s.ctx.config={};s.ctx.monitor=true;await receive(s,data());
 assert.match(s.node('#patientSummaryCounts').textContent,/최신 판정 1/);
 await s.node('#notifyLink').onclick();assert.equal(s.node('#patientPanel').open,false);
});
test('failed panel opening preserves attention and storage failure remains usable',async()=>{
 const s=setup();s.ctx.sid='one';s.ctx.config={};s.ctx.sessionStorage.setItem=()=>{throw Error('denied');};await receive(s,data());
 s.node('#patientPanel').show=()=>{throw Error('cannot open');};await s.node('#notifyLink').onclick();
 assert(s.node('#notifyLink').classList.contains('has-new-patients'));
});
test('detail keeps original version and blocks quoting after replacement',async()=>{
 const s=setup();s.ctx.sid='one';s.ctx.config={};await receive(s,data());await s.node('#notifyLink').onclick();await s.run('openPatientDetail("a")');
 await receive(s,data(['b']));assert.match(s.node('#patientBody').innerHTML,/가상 판정 a/);
 assert.match(s.node('#patientVersion').innerHTML,/새 판정 도착/);assert.equal(s.node('#patientReview').disabled,true);
});
test('unlinked panel explains the empty list',async()=>{
 const s=setup();s.ctx.sid='one';s.ctx.config={};await receive(s,{...data([]),linked:false});await s.node('#notifyLink').onclick();
 assert.match(s.node('#patientList').innerHTML,/연결/);
});
test('replacement keeps detail DOM and marks the changed patient row',async()=>{
 const s=setup();s.ctx.sid='one';s.ctx.config={};await receive(s,data());await s.node('#notifyLink').onclick();await s.run('openPatientDetail("a")');
 const node=s.node('#patientBody');let html=node.innerHTML,rewrites=0;
 Object.defineProperty(node,'innerHTML',{get:()=>html,set:v=>{html=v;rewrites++;}});
 await receive(s,data(['b']));assert.equal(rewrites,0,'must retain focus and expanded details');
 assert.match(s.node('#patientList').innerHTML,/열람 후 변경/);
 assert.equal(s.node('#patientReview').disabled,true);
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
