const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(){assert.ok(fs.existsSync('prototype/static/linkone-current.js'),'current UI missing');const ctx=vm.createContext({setInterval(){},Date});vm.runInContext(fs.readFileSync('prototype/static/linkone-current.js','utf8'),ctx);return ctx;}
test('live counts used only for same room and not superseded',()=>{
 const c=setup();c.data={session:{id:'s',linkone:{room_id:'r'},facts:{total:5}},live_situation:{session_id:'s',room_id:'r',summary:{total:8,rescued:3},status:'ready'}};
 assert.equal(vm.runInContext('currentSituationView(data).summary.total',c),8);
 c.data.live_situation.superseded=true;assert.equal(vm.runInContext('currentSituationView(data).usable',c),false);
 c.data.live_situation.room_id='else';assert.equal(vm.runInContext('currentSituationView(data).usable',c),false);
});
test('stale cached counts remain identifiable',()=>{
 const c=setup();c.data={session:{id:'s',linkone:{room_id:'r'},facts:{}},live_situation:{session_id:'s',room_id:'r',summary:{total:8},stale:true,status:'error'}};
 assert.equal(vm.runInContext('currentSituationView(data).usable',c),true);
 assert.match(vm.runInContext('currentSituationView(data).label',c),/갱신 지연/);
});
test('newer state timestamp wins over older voice record',()=>{
 const c=setup();c.data={person:[{id:'a',name:'A'},{id:'b',name:'B'}],person_state:[{person_id:'a',updated_at:'2026-09-30T10:00:00Z'},{person_id:'b',updated_at:'2026-09-30T09:00:00Z'}],recent_records:[{person_id:'a',server_at:'2026-09-30T08:00:00Z'}]};c.linkText=String;
 assert.equal(vm.runInContext('currentRosterRows(data,"",{column:4,direction:-1})[0].id',c),'a');
});
test('selected older report is not described as current verified material',()=>{
 const c=setup();assert.equal(vm.runInContext('typeof currentBasisLabel',c),'function');
 assert.match(vm.runInContext('currentBasisLabel({basis_matches:true,basis_snapshot_id:"new",basis_revision:3},{linkone_snapshot_id:"old",based_on_version:1})',c),/이전 수신본/);
});
