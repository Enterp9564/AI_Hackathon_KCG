/* Isolated synthetic source. No real patients, external DB, or AI calls. */
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{spawn}=require('node:child_process');
(async()=>{
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'haeon-vessel-ui-'));
 const child=spawn(process.env.PYTHON||'python3',['-m','prototype.tests.serve_patient_ui'],{env:{...process.env,HAEON_TEST_VESSEL:'1'},stdio:['ignore','pipe','pipe']});
 let log='',stderr='',browser;child.stdout.on('data',v=>log+=v);child.stderr.on('data',v=>stderr+=v);
 try{
  const deadline=Date.now()+15000;
  while(!log.includes('PATIENT_UI')){if(Date.now()>deadline||child.exitCode!==null)throw Error(stderr||'timeout');await new Promise(r=>setTimeout(r,50));}
  const base=log.match(/PATIENT_UI (\S+)/)[1],config=await(await fetch(base+'/api/config')).json();
  async function api(p){const r=await fetch(base+p,{headers:{'X-Session-Token':config.token}});assert(r.ok);return r.json();}
  const sessions=await api('/api/sessions'),a=sessions.find(s=>s.title==='가상 환자 8명 점검');
  browser=await chromium.launch({headless:true,channel:'chrome'});const page=await browser.newPage({viewport:{width:1920,height:1080}}),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')writes.push(r.url());});
  await page.goto(base);await page.evaluate(id=>localStorage.setItem('situation-room:last-session',id),a.id);await page.reload();
  await page.waitForFunction(()=>document.querySelector('#patientSummaryCounts').textContent.includes('선체경사 경고 기록 2건'));
  await page.locator('#notifyLink').click();await page.locator('#patientExpand').click();assert.equal(await page.locator('[data-patient]').count(),10);
  assert.match(await page.locator('[data-patient]').first().textContent(),/측정 지연/);
  await page.locator('#alertSort-time').click();assert.match(await page.locator('[data-patient]').first().textContent(),/환자 00000001/);
  await page.locator('#alertSort-time').click();assert.match(await page.locator('[data-patient]').first().textContent(),/측정 지연/);
  await page.locator('#alertType').selectOption('patient');await page.locator('#alertSort-name').click();assert.match(await page.locator('[data-patient]').first().textContent(),/00000001/);
  await page.locator('#alertSort-name').click();assert.match(await page.locator('[data-patient]').first().textContent(),/00000008/);
  for(const key of ['situation','content']){await page.locator('#alertSort-'+key).click();assert.match(await page.locator('#alertSort-'+key).textContent(),/▲/);await page.locator('#alertSort-'+key).click();assert.match(await page.locator('#alertSort-'+key).textContent(),/▼/);}
  assert.equal(writes.length,0);await page.locator('#alertType').selectOption('vessel');assert.equal(await page.locator('[data-patient]').count(),2);
  await page.locator('#patientFilter').selectOption('RAPID');assert.equal(await page.locator('[data-patient]').count(),1);
  await page.locator('[data-patient]').first().click();assert.match(await page.locator('#patientBody').textContent(),/출처 확인은 위험 해소/);assert.equal(await page.locator('#patientReview').count(),0);
  await page.waitForFunction(()=>document.querySelector('#patientSummaryCounts').textContent.includes('미열람 9'));
  assert.equal(writes.filter(p=>p.endsWith('/vessel-alert-seen')).length,1);
  const current=await api(`/api/sessions/${a.id}/patient-alerts`);assert.equal(current.vessel.items.find(i=>i.original.kind==='RAPID').original.ack_count,0);
  await page.locator('#patientBack').click();await page.locator('#patientFilter').selectOption('source_unacked');assert.equal(await page.locator('[data-patient]').count(),1);
  await page.locator('#patientFilter').selectOption('all');await page.locator('#alertType').selectOption('all');await page.locator('#alertSort-time').click();
  await page.screenshot({path:path.join(folder,'combined-alerts.png')});
  await page.setViewportSize({width:390,height:844});await page.locator('#alertType').selectOption('vessel');await page.locator('[data-patient]').first().click();
  assert(await page.locator('#patientPanel').evaluate(e=>e.scrollWidth<=e.clientWidth+1));await page.screenshot({path:path.join(folder,'vessel-mobile.png')});
  assert.equal((await api('/api/sessions/'+a.id)).runs.length,0);assert(!writes.some(p=>p.endsWith('/message')||p.endsWith('/review')||p.endsWith('/ack')));assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'PASS',artifacts:folder,checks:'combined latest order; four headers both directions; type/kind/ack filters; separate local read; source ack untouched; mobile; zero AI'}));
 }finally{if(browser)await browser.close();child.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
