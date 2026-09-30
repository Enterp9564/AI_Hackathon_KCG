const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync('prototype/static/app.js','utf8');
function run(code){const c=vm.createContext({});vm.runInContext(src.slice(src.indexOf('function criticReviewState'),src.indexOf('function renderExecutionStatus')),c);return vm.runInContext(code,c);}
test('OFF specialists finished go straight to synthesis',()=>{
 assert.match(src,/function criticReviewState/);
 assert.equal(run(`executionPhase({status:'running',critic_enabled:false,decision:{tasks:[{role:'sar'}]}},[{role:'sar',status:'completed'}])`),'synthesis');
});
test('history follows actual run, failures not success',()=>{
 assert.match(src,/function criticReviewState/);
 assert.equal(run(`criticReviewState({critic_enabled:false,critic_review:{status:'skipped'}},[])`),'skipped');
 assert.equal(run(`criticReviewState({},[{role:'critic',status:'failed'}])`),'failed');
 assert.equal(run(`criticReviewState({},[])`),'unknown');
});
