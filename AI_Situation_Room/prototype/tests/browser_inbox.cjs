/* Run with Playwright available in NODE_PATH. Uses its own DB and loopback ports. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {once}=require('node:events');

(async()=>{
  const folder=fs.mkdtempSync(path.join(os.tmpdir(),'kcg-mcp-browser-'));
  const tokens={'link-one':'test-link-token-'.repeat(3),'resaid-ai':'test-resaid-token-'.repeat(3)};
  const credentials=path.join(folder,'clients.json');
  fs.writeFileSync(credentials,JSON.stringify(tokens),{mode:0o600});
  const child=spawn(process.env.PYTHON||'python3',['-m','prototype.server','--port','0','--db',path.join(folder,'test.sqlite'),
      '--mcp-port','0','--mcp-tokens',credentials],{stdio:['ignore','pipe','pipe']});
  let output='',errors='',browser;
  child.stdout.on('data',data=>output+=data.toString());child.stderr.on('data',data=>errors+=data.toString());
  try{
    const deadline=Date.now()+10000;
    while(!/AI 상황실: http/.test(output)){
      if(child.exitCode!==null||Date.now()>deadline)throw new Error('Test server failed: '+errors);
      await new Promise(r=>setTimeout(r,50));
    }
    const base=output.match(/AI 상황실: (http:\/\/[^\s]+)/)[1];
    const mcp='http://127.0.0.1:'+output.match(/MCP 수신: 127.0.0.1:(\d+)/)[1]+'/mcp';
    const config=await (await fetch(base+'/api/config')).json();
    async function api(route,data){
      const response=await fetch(base+route,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Session-Token':config.token},body:data===undefined?undefined:JSON.stringify(data)});
      const result=await response.json();assert(response.ok,JSON.stringify(result));return result;
    }
    const a=await api('/api/sessions',{title:'A호 사고 · 연동 검증',mode:'demo'});
    const b=await api('/api/sessions',{title:'B호 사고 · 다른 사건',mode:'demo'});
    async function submit(project,id,incident='incident-a',content='구조 대상자 1명의 상태 변화가 보고되었습니다. <script>검증용 원문</script>'){
      const response=await fetch(mcp,{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-11-25','Authorization':'Bearer '+tokens[project]},
        body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'submit_field_report',arguments:{report_id:id,incident_id:incident,incident_title:incident==='incident-a'?'A호 사고':'B호 사고',reported_at:'2026-09-27T14:32:00+09:00',content}}})});
      const result=await response.json();assert.equal(result.result.isError,false);return result.result.structuredContent.receipt_id;
    }
    browser=await chromium.launch({headless:true,...(process.env.CHROME_CHANNEL?{channel:process.env.CHROME_CHANNEL}:{})});
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));
    await page.goto(base);
    await page.evaluate(id=>localStorage.setItem('situation-room:last-session',id),a.id);
    await page.reload();
    await page.locator('#sessionTitle').filter({hasText:'A호 사고'}).waitFor();
    await page.locator('#notifyLink').click();
    await page.locator('.inbox-link summary').click();
    await page.locator('#externalIncident').fill('incident-a');
    await page.locator('#inboxLinkForm button').click();
    await page.locator('#inboxLinks').filter({hasText:'incident-a'}).waitFor();
    await page.locator('#closeInbox').click();
    await page.locator('#simulationMode').click();
    await page.locator('#prompt').fill('작성 중인 현장 지시 초안');
    await page.locator('#assumptions').fill('지원 함정 1척 가용 불가 가정');
    const r1=await submit('link-one','r1');
    assert.equal(await submit('link-one','r1'),r1);
    await page.locator('#notifyLink.has-unseen').waitFor();
    assert.equal((await api('/api/sessions/'+a.id)).runs.length,0);
    await page.locator('#notifyLink').click();
    const card=page.locator(`[data-report="${r1}"]`);
    await card.locator('.inbox-original').filter({hasText:'<script>'}).waitFor();
    await page.screenshot({path:path.join(folder,'inbox-desktop.png'),fullPage:true});
    await card.getByRole('button',{name:'인용하여 전송',exact:true}).click();
    await page.waitForFunction(()=>!document.querySelector('#inboxPanel').open);
    assert.equal(await page.locator('#prompt').inputValue(),'작성 중인 현장 지시 초안');
    assert.equal(await page.locator('#assumptions').inputValue(),'지원 함정 1척 가용 불가 가정');
    assert.match(await page.locator('#simulationMode').getAttribute('class'),/active/);
    const end=Date.now()+15000;
    let snap;
    do{snap=await api('/api/sessions/'+a.id);if(snap.runs[0]?.status==='completed')break;await page.waitForTimeout(100);}while(Date.now()<end);
    assert.equal(snap.runs.length,1);assert.equal(snap.runs[0].status,'completed');assert.deepEqual(snap.session.facts,{});
    assert.match(snap.messages[0].content,/\[Link-One 수신 정보 인용\]/);
    await api('/api/sessions/'+a.id+'/message',{inbox_report_id:r1});
    assert.equal((await api('/api/sessions/'+a.id)).runs.length,1);
    const r2=await submit('link-one','r2');
    await page.locator('#notifyLink').click();
    await page.locator(`[data-report="${r2}"] [data-action="later"]`).click();
    await page.waitForFunction(()=>!document.querySelector('#inboxPanel').open);
    assert.equal((await api('/api/inbox')).reports.find(r=>r.id===r2).status,'deferred');
    await page.locator('#notifyLink').click();
    await page.locator(`[data-report="${r2}"] [data-action="reject"]`).click();
    await page.locator(`[data-report="${r2}"] .small-badge`).filter({hasText:'반영 안 함'}).waitFor();
    assert.equal((await api('/api/sessions/'+a.id)).runs.length,1);
    await api('/api/sessions/'+b.id+'/inbox-link',{project:'link-one',incident_id:'incident-b'});
    const r3=await submit('link-one','r3','incident-b');
    const other=page.locator(`[data-report="${r3}"]`);
    await other.waitFor();assert(await other.locator('[data-action="quote"]').isDisabled());
    await other.locator('[data-action="switch"]').click();
    await page.locator('#inboxSession').filter({hasText:'B호 사고'}).waitFor();
    assert.equal(await other.locator('[data-action="quote"]').isDisabled(),false);
    await page.locator('#closeInbox').click();
    await api('/api/sessions/'+b.id+'/inbox-link',{project:'resaid-ai',incident_id:'incident-b'});
    const r4=await submit('resaid-ai','r1','incident-b','환자의 의식 상태가 변했다고 보고되었습니다.');
    await page.locator('#notifyResaid').click();
    await page.locator(`[data-report="${r4}"]`).waitFor();
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(folder,'inbox-mobile.png'),fullPage:true});
    const bounds=await page.locator('#inboxPanel').boundingBox();assert(bounds.x>=0&&bounds.x+bounds.width<=390);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#inboxPanel').evaluate(el=>el.open),false);
    assert.deepEqual(pageErrors,[]);
    console.log('Browser PASS: project alerts, escaped original, one approved run, draft/mode retained, later/reject, wrong-incident guard/switch, RESAID, mobile panel, Escape, no page errors.');
    console.log('Evidence: '+folder);
  }finally{
    if(browser)await browser.close();
    child.kill('SIGINT');await once(child,'exit');
    fs.unlinkSync(credentials);
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
