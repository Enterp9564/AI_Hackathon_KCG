const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('prototype/static/app.js','utf8');
const api=source.slice(source.indexOf('async function api('),source.indexOf('\nfunction toast('));
const reply=(status,data)=>({status,ok:status>=200&&status<300,json:async()=>data});
async function run(responses){const calls=[],ctx={config:{token:'old',live_available:true},AbortController,setTimeout,clearTimeout,fetch:async(path,opts)=>{calls.push({path,opts});const r=responses.shift();if(r instanceof Error)throw r;return r;}};vm.createContext(ctx);vm.runInContext(api,ctx);return {ctx,calls};}
(async()=>{
 let t=await run([reply(403,{error:'허용되지 않은 쓰기 요청입니다.'}),reply(200,{token:'new',live_available:true}),reply(202,{id:'ok'})]);
 assert.equal((await t.ctx.api('/api/sessions/s/linkone-sync',{})).id,'ok');
 assert.equal(t.calls.length,3);assert.equal(t.calls[2].opts.headers['X-Session-Token'],'new');assert.equal(t.calls[0].opts.body,t.calls[2].opts.body);
 t=await run([reply(403,{error:'허용되지 않은 쓰기 요청입니다.'}),reply(403,{error:'origin denied'})]);await assert.rejects(t.ctx.api('/api/sessions/s/delete',{}));assert.equal(t.calls.length,2);
 t=await run([reply(403,{error:'허용되지 않은 쓰기 요청입니다.'}),reply(200,{token:'new'}),reply(403,{error:'denied again'})]);await assert.rejects(t.ctx.api('/api/sessions/s/delete',{}));assert.equal(t.calls.length,3);
 t=await run([new Error('network lost')]);await assert.rejects(t.ctx.api('/api/sessions/s/message',{request_id:'stable'}));assert.equal(t.calls.length,1);
 console.log('Token refresh: rejected write retried once; origin rejection and network errors never replayed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
