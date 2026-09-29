// Render the real flow against recorded state shapes; no model or server calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('prototype/static/app.js','utf8');
const flow = {innerHTML:'',querySelectorAll:()=>[]};
const context = {runId:null,optimisticPrompt:'',snapshot:null,$:()=>flow,
  esc:v=>String(v??''),time:()=>'',roleNames:{intel:'정보요원',sar:'수색구조요원',resource:'자원지원요원'},
  statuses:{running:'검토 중',completed:'보고 완료',assigned:'임무 수신',failed:'작업 실패'},
  requestHTML:()=>'',dispatchHTML:()=>'',list:()=>''};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function currentRun('),source.indexOf('function executionStatusHTML('))+
  source.slice(source.indexOf('function statusBadge('),source.indexOf('function openFinal(')),context);
const run = {id:'run',status:'running',based_on_version:1,prompt:'검토',decision:{tasks:[{role:'intel'},{role:'sar'}]}};
const task = (role,status)=>({id:role,run_id:'run',role,status});
function render(tasks,overrides={}) {
  const current={...run,...overrides};context.renderFlow({runs:[current],tasks});
  return {html:flow.innerHTML,progress:context.progressState(current,tasks),activity:context.activityState(current,tasks)};
}
function cardClass(html,name) {return html.match(new RegExp('class="([^"]*\\b'+name+'\\b[^"]*)"'))?.[1]||'';}
let state=render([task('intel','completed'),task('sar','completed'),task('critic','running')]);
assert.match(cardClass(state.html,'critic-card'),/activity-glow/,'Running critic must be highlighted');
assert.doesNotMatch(cardClass(state.html,'command-card'),/activity-glow/,'Commander is waiting for the critic');
assert.match(state.progress.phase,/검증/);assert.match(state.activity.label,/검증/);
assert.doesNotMatch(state.html,/class="status running">검토 중<\/span>/,'Commander badge must also show waiting');
state=render([task('intel','running'),task('sar','running')]);
assert.equal((state.html.match(/class="agent-card running activity-glow"/g)||[]).length,2);
assert.doesNotMatch(cardClass(state.html,'command-card'),/activity-glow/);
state=render([task('intel','completed'),task('sar','completed')]);
assert.doesNotMatch(cardClass(state.html,'command-card'),/activity-glow/,'Report handoff is not final synthesis');
assert.match(state.progress.phase,/검증/);
state=render([task('intel','completed'),task('sar','completed'),task('critic','assigned')]);
assert.doesNotMatch(cardClass(state.html,'critic-card'),/activity-glow/,'Assigned is not running');
assert.doesNotMatch(cardClass(state.html,'command-card'),/activity-glow/);
state=render([task('intel','completed'),task('sar','completed'),task('critic','completed')]);
assert.match(cardClass(state.html,'command-card'),/activity-glow/);
assert.doesNotMatch(cardClass(state.html,'critic-card'),/activity-glow/);
assert.match(state.progress.phase,/종합/);
state=render([],{decision:null});assert.match(cardClass(state.html,'command-card'),/activity-glow/);
for(const status of ['completed','failed','interrupted','stale','queued']) {
  state=render([task('critic','running')],{status});
  assert.doesNotMatch(state.html,/activity-glow/,`No ongoing glow for ${status}`);
}
console.log('Activity: routing, parallel work, verification wait/work, synthesis and terminal states passed.');
