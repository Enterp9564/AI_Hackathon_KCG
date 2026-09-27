// Exercise the actual shared send() with a small DOM/API boundary stub.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('prototype/static/app.js','utf8');
const send = source.slice(source.indexOf('async function send('),source.indexOf("\n$('#newSession')"));
(async()=>{
  const input={value:'작성 중인 중요한 초안'}, assumptions={value:'기존 비교 가정'}, button={disabled:false};
  const requests=[];
  const context={sid:'s1',sending:false,requestKind:'simulation',retries:new Map(),drafts:new Map(),
    optimisticPrompt:'',runId:null,contentSignature:'',snapshot:null,
    $:id=>({'#prompt':input,'#assumptions':assumptions,'#send':button}[id]),
    crypto:require('node:crypto').webcrypto,toast:()=>{},showOptimistic:()=>{},renderFlow:()=>{},
    saveDraft:()=>{},refresh:async()=>{},api:async(path,payload)=>{requests.push({path,payload});return {id:'run'};}};
  vm.createContext(context);vm.runInContext(send,context);
  const report={id:'r1',session_id:'s1',project:'link-one',original:{content:'미확인 현장 보고'}};
  assert.equal(await context.send({report}),true);
  assert.equal(input.value,'작성 중인 중요한 초안');
  assert.equal(assumptions.value,'기존 비교 가정');
  assert.equal(context.requestKind,'simulation');
  assert.equal(requests[0].payload.inbox_report_id,'r1');
  assert.equal(requests[0].payload.kind,'analysis');
  assert.equal(context.retries.size,0);
  assert.equal(await context.send({report:{...report,session_id:'other'}}),false);
  assert.equal(requests.length,1);
  context.api=async()=>{throw new Error('timeout');};
  assert.equal(await context.send({report}),false);
  assert.equal(input.value,'작성 중인 중요한 초안');
  assert.equal(button.disabled,false);
  console.log('Shared send: quote uses existing endpoint, preserves draft/mode, blocks wrong session, handles failure.');
})().catch(e=>{console.error(e);process.exitCode=1;});
