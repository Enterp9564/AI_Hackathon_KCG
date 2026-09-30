/* Synthetic local API/server only. No remote DB, patient records, or model calls. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
(async()=>{
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'haeon-patient-browser-'));
 const child=spawn(process.env.PYTHON||'python3',['-m','prototype.tests.serve_patient_ui'],{stdio:['ignore','pipe','pipe']});
 let output='',stderr='',browser;child.stdout.on('data',b=>output+=b);child.stderr.on('data',b=>stderr+=b);
 try{
  const deadline=Date.now()+15000;
  while(!output.includes('PATIENT_UI')){if(child.exitCode!==null||Date.now()>deadline)throw Error(stderr||'server timeout');await new Promise(r=>setTimeout(r,50));}
  const base=output.match(/PATIENT_UI (\S+)/)[1];
  const config=await(await fetch(base+'/api/config')).json();
  async function api(url,body){const r=await fetch(base+url,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-Session-Token':config.token},body:body?JSON.stringify(body):undefined});assert(r.ok);return r.json();}
  const sessions=await api('/api/sessions'),a=sessions.find(s=>s.title==='가상 환자 8명 점검'),b=sessions.find(s=>s.id!==a.id);
  browser=await chromium.launch({headless:true,channel:'chrome'});
  const page=await browser.newPage({viewport:{width:1920,height:1080}}),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')writes.push(r.url());});
  await page.goto(base);await page.evaluate(id=>localStorage.setItem('situation-room:last-session',id),a.id);await page.reload();
  const wait=fn=>page.waitForFunction(fn);
  await wait(()=>document.querySelector('#patientSummaryCounts').textContent.includes('최신 판정 8명'));
  assert(await page.locator('#notifyLink').evaluate(e=>e.classList.contains('has-new-patients')));
  await page.locator('#prompt').fill('작성 중인 초안 보존');await page.locator('#notifyLink').click();
  assert.equal(await page.locator('#notifyLink').evaluate(e=>e.classList.contains('has-new-patients')),false);
  assert.match(await page.locator('#patientSummaryCounts').textContent(),/미열람 8/);assert.equal(writes.length,0);
  await page.locator('#patientExpand').click();assert.equal(await page.locator('[data-patient]').count(),8);
  const fits=await page.locator('#patientList').evaluate(e=>{const r=e.getBoundingClientRect();return [...e.querySelectorAll('[data-patient]')].every(b=>{const x=b.getBoundingClientRect();return x.top>=r.top&&x.bottom<=r.bottom+1;});});assert(fits,'8 complete rows visible at 1920x1080');
  await page.screenshot({path:path.join(folder,'eight-patients.png')});
  await page.locator('#patientFilter').selectOption('IMMEDIATE');assert.equal(await page.locator('[data-patient]').count(),5);
  await page.locator('#patientFilter').selectOption('all');await page.locator('#patientSearch').fill('가상 환자 A');assert.equal(await page.locator('[data-patient]').count(),1);
  await page.locator('#patientSearch').fill('');assert.equal(await page.locator('[data-patient]').count(),8);assert.equal(writes.length,0);
  const first=page.locator('[data-patient]').first();await first.click();
  await wait(()=>document.querySelector('#patientSummaryCounts').textContent.includes('미열람 7'));
  assert.equal(await page.locator('[data-patient]').count(),8);assert(await page.locator('#patientReview').isEnabled());
  await page.locator('#patientBody details').nth(1).locator('summary').click();
  await page.locator('#patientBody details').nth(1).locator('summary').focus();
  const original=await page.locator('#patientBody').textContent(),cache=await api(`/api/sessions/${a.id}/patient-alerts`),oldID=await first.getAttribute('data-patient');
  const replacement=structuredClone(cache);const changed=replacement.items.find(i=>i.id===oldID);changed.id='synthetic-revision';changed.seen_at=null;changed.original.summary='새 가상 판정';replacement.unread=8;
  await page.route('**/patient-alerts',r=>r.fulfill({json:replacement}));
  await wait(()=>document.querySelector('#patientVersion').textContent.includes('새 판정 도착'));
  assert.equal(await page.locator('#patientBody').textContent(),original);assert(await page.locator('#patientReview').isDisabled());
  assert(await page.locator('#patientBody details').nth(1).evaluate(e=>e.open));
  assert(await page.locator('#patientBody details').nth(1).locator('summary').evaluate(e=>e===document.activeElement));
  assert.match(await page.locator('.patient-row.selected').textContent(),/열람 후 변경/);
  assert(await page.locator('#notifyLink').evaluate(e=>e.classList.contains('has-new-patients')));
  await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await page.locator('#notifyLink').evaluate(e=>getComputedStyle(e).animationName),'none');
  await page.locator('.patient-row.selected').focus();changed.id='synthetic-revision-2';
  await page.waitForFunction(()=>document.querySelector('.patient-row.selected')?.dataset.patient==='synthetic-revision-2');
  assert(await page.locator('.patient-row.selected').evaluate(e=>e===document.activeElement));
  await page.locator('#notifyLink').click();assert.equal(await page.locator('#notifyLink').evaluate(e=>e.classList.contains('has-new-patients')),false);
  await page.locator('#patientClose').click();assert.equal(await page.locator('#prompt').inputValue(),'작성 중인 초안 보존');
  await page.unroute('**/patient-alerts');await page.locator(`[data-session="${b.id}"]`).click();
  await wait(()=>document.querySelector('#patientSummaryCounts').textContent.includes('최신 판정 0명'));
  await page.locator(`[data-session="${a.id}"]`).click();await wait(()=>document.querySelector('#patientSummaryCounts').textContent.includes('최신 판정 8명'));
  await page.setViewportSize({width:1366,height:768});await page.locator('#patientOverviewOpen').click();
  assert(await page.locator('#patientClose').isVisible());await page.locator('#patientClose').click();
  await page.setViewportSize({width:390,height:844});await page.locator('#patientOverviewOpen').click();
  assert(await page.locator('[data-patient]').first().isVisible());await page.locator('[data-patient]').first().click();assert(await page.locator('#patientBody').isVisible());
  assert(await page.locator('#patientPanel').evaluate(e=>e.scrollWidth<=e.clientWidth+1));
  await page.screenshot({path:path.join(folder,'mobile-detail.png')});await page.locator('#patientBack').click();assert(await page.locator('[data-patient]').first().isVisible());
  await page.keyboard.press('Escape');assert.equal(await page.locator('#patientPanel').evaluate(e=>e.open),false);
  for(const width of [320,768,1024,1440]){
   await page.setViewportSize({width,height:900});await page.locator('#patientOverviewOpen').click();
   assert(await page.locator('#patientPanel').evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&e.scrollWidth<=e.clientWidth+1;}));
   await page.locator('#patientClose').click();
  }
  await page.setViewportSize({width:1920,height:1080});await page.locator('#notifyLink').focus();await page.keyboard.press('Enter');assert(await page.locator('#patientPanel').evaluate(e=>e.open));
  await page.locator('#patientClose').click();await page.emulateMedia({reducedMotion:'reduce'});
  await api(`/api/sessions/${a.id}/pin`,{});const wall=await browser.newPage({viewport:{width:1920,height:1080}});await wall.goto(base+'/monitor');
  await wall.waitForFunction(()=>document.querySelector('#patientSummaryCounts').textContent.includes('최신 판정 8명'));
  assert.equal(await wall.locator('#patientOverviewOpen').isVisible(),false);
  assert.equal((await api('/api/sessions/'+a.id)).runs.length,0);assert.equal((await api('/api/sessions/'+b.id)).runs.length,0);
  assert(!writes.some(u=>u.endsWith('/message')));assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'PASS',artifacts:folder,checks:'8-row desktop, button attention/read separation, revision while reading, stale quote disabled, draft, session switch, 1366/390 layout, keyboard, wallboard, zero AI'}));
 }finally{if(browser)await browser.close();child.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
