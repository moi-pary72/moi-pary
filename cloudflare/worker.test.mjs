import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{check} from './worker.js';
const NOW=new Date('2026-11-17T12:00:00Z');
const status=(date,errors=[])=>({checked_at:date,errors});
const recent=(date,state='completed')=>({workflow_runs:[{created_at:date,status:state}]});
const fixture=async (source, runs, opts={})=>{
  const old=globalThis.fetch, calls=[];
  globalThis.fetch=async(url,arg={})=>{
    const u=new URL(url);calls.push([u.hostname,u.pathname,arg.method||'GET']);
    if(u.hostname==='raw.githubusercontent.com')return Response.json(source);
    if(u.pathname.endsWith('/sync.yml/runs'))return Response.json(runs);
    if(u.pathname.endsWith('/dispatches'))return new Response(null,{status:opts.failDispatch?403:204});
    throw Error('Unexpected request');
  };
  try{return {result:await check({GITHUB_TOKEN:opts.secret===false?undefined:'dummy'},NOW),calls};}
  finally{globalThis.fetch=old;}
};
test('fresh status uses public check only',async()=>{
  const r=await fixture(status('2026-11-17T11:30:00Z'),recent('2026-11-17T10:00:00Z'));
  assert.equal(r.result,'fresh');assert.equal(r.calls.length,1);
});
test('stale status but recently ran, no duplicate',async()=>{
  const r=await fixture(status('2026-11-17T10:00:00Z'),recent('2026-11-17T11:30:00Z'));
  assert.equal(r.result,'github-run-cooldown');assert.equal(r.calls.length,2);
});
test('stale status with running job, no duplicate',async()=>{
  const r=await fixture(status('2026-11-17T10:00:00Z'),recent('2026-11-17T09:00:00Z','in_progress'));
  assert.equal(r.result,'github-run-active');assert.equal(r.calls.length,2);
});
test('stale and no recent job, one dispatch',async()=>{
  const r=await fixture(status('2026-11-17T10:00:00Z'),recent('2026-11-17T09:00:00Z'));
  assert.equal(r.result,'github-dispatch-accepted-not-published');assert.equal(r.calls.length,3);
  assert.deepEqual(r.calls[2].slice(1),['/repos/moi-pary72/moi-pary/dispatches','POST']);
});
test('source errors never dispatch',async()=>{
  const r=await fixture(status('2026-11-17T10:00:00Z',['Yandex source unavailable']),recent('2026-11-17T08:00:00Z'));
  assert.equal(r.result,'source-error');assert.equal(r.calls.length,1);
});
test('missing secret prevents dispatch',async()=>{
  await assert.rejects(()=>fixture(status('2026-11-17T10:00:00Z'),recent('2026-11-17T08:00:00Z'),{secret:false}),/Missing GITHUB_TOKEN/);
});
test('failed dispatch is not treated as success',async()=>{
  await assert.rejects(()=>fixture(status('2026-11-17T10:00:00Z'),recent('2026-11-17T08:00:00Z'),{failDispatch:true}),/HTTP 403/);
});
test('health endpoint does not trigger tasks',async()=>{
  const old=globalThis.fetch;globalThis.fetch=()=>{throw Error('network should not be used')};
  try {const x=await worker.fetch(new Request('https://example.test/health'),{GITHUB_TOKEN:'secret'});
    assert.equal((await x.json()).configured,true);
    assert.equal((await worker.fetch(new Request('https://example.test/trigger'),{})).status,404);
  }finally{globalThis.fetch=old;}
});
