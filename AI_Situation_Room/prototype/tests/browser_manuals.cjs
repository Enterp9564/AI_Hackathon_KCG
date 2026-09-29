/* Uses only a new temporary DB and DEMO generation. Search is real lexical retrieval. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
(async()=>{
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'haeon-manual-ui-'));
 const child=spawn(process.env.PYTHON||'python3',['-m','prototype.server','--port','0','--db',path.join(folder,'room.sqlite'),'--manual-search','lexical'],{stdio:['ignore','pipe','pipe']});
 let output='',errors='',browser;
 child.stdout.on('data',b=>output+=b);child.stderr.on('data',b=>errors+=b);
 try{
  const end=Date.now()+15000;
  while(!/AI 상황실: http/.test(output)){if(child.exitCode!==null||Date.now()>end)throw Error(errors||'server timeout');await new Promise(r=>setTimeout(r,50));}
  const base=output.match(/AI 상황실: (http:\/\/\S+)/)[1];
  const config=await(await fetch(base+'/api/config')).json();
  async function api(route,data){const r=await fetch(base+route,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Session-Token':config.token},body:data===undefined?undefined:JSON.stringify(data)});assert(r.ok);return r.json();}
  const a=await api('/api/sessions',{title:'SAR 연결 검증',mode:'demo'});
  const b=await api('/api/sessions',{title:'다른 사건',mode:'demo'});
  const run=await api(`/api/sessions/${a.id}/message`,{prompt:'화재와 실종자 수색 대응을 전체 검토해줘',request_id:'one',kind:'analysis'});
  let snap;
  const deadline=Date.now()+15000;
  do{snap=await api('/api/sessions/'+a.id);if(snap.runs[0].status==='completed')break;await new Promise(r=>setTimeout(r,50));}while(Date.now()<deadline);
  assert.equal(snap.runs[0].status,'completed');assert(snap.manual_contexts.length>=3);
  browser=await chromium.launch({headless:true,channel:process.env.CHROME_CHANNEL||'chrome'});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),jsErrors=[];
  page.on('pageerror',e=>jsErrors.push(e.message));
  await page.goto(base);await page.evaluate(id=>localStorage.setItem('situation-room:last-session',id),a.id);await page.reload();
  await page.locator('#sessionTitle').filter({hasText:'SAR 연결 검증'}).waitFor();
  await page.locator('#prompt').fill('작성 중인 초안 보존');
  await page.locator(`[data-report="${run.id}"]`).click();
  await page.getByRole('button',{name:/최종 종합에 전달한 근거/}).click();
  await page.locator('#modalTitle').filter({hasText:'실행 당시 제공 근거'}).waitFor();
  await page.getByText('적용 제한',{exact:true}).first().waitFor();
  assert(await page.getByRole('link',{name:'로컬 원본 PDF',exact:true}).count()>0);
  const link=await page.getByRole('link',{name:'로컬 원본 PDF',exact:true}).first().getAttribute('href');
  const pdf=await fetch(base+link.split('#')[0]);assert.equal(pdf.headers.get('content-type'),'application/pdf');
  assert(Buffer.from(await pdf.arrayBuffer()).subarray(0,5).equals(Buffer.from('%PDF-')));
  await page.screenshot({path:path.join(folder,'manual-desktop.png'),fullPage:true});
  await page.keyboard.press('Escape');assert.equal(await page.locator('#prompt').inputValue(),'작성 중인 초안 보존');
  await page.setViewportSize({width:390,height:844});
  await page.locator(`[data-report="${run.id}"]`).click();
  await page.getByRole('button',{name:/최종 종합에 전달한 근거/}).click();
  await page.locator('#modalTitle').filter({hasText:'실행 당시 제공 근거'}).waitFor();
  assert(await page.locator('#modal').evaluate(e=>e.scrollWidth<=e.clientWidth+2));
  await page.screenshot({path:path.join(folder,'manual-mobile.png'),fullPage:true});
  await page.keyboard.press('Escape');
  await page.locator(`[data-session="${b.id}"]`).click();
  await page.locator('#sessionTitle').filter({hasText:'다른 사건'}).waitFor();
  assert.equal((await api('/api/sessions/'+b.id)).manual_contexts.length,0);
  assert.deepEqual(jsErrors,[]);
  console.log(JSON.stringify({passed:true,artifacts:folder,contexts:snap.manual_contexts.length,jsErrors}));
 }finally{if(browser)await browser.close();child.kill('SIGINT');}
})().catch(e=>{console.error(e);process.exitCode=1;});
