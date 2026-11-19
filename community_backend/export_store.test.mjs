import test from 'node:test';import assert from 'node:assert/strict';import worker,{validate} from './worker.mjs';import {checkExport} from './export_store.mjs';import {localEnv} from './local_server.mjs';
const source=()=>({schema_version:1,engine_version:'0.2.7-test8',sequence:'EJ',body_ids:['399','599'],dates_jd_tdb:[2460000,2461000],branches:[[0,true]],dsm_controls:[],classification:'pass',solved_at:'2026-01-01T00:00:00Z',metrics:{launch_c3_km2_s2:11,total_dsm_kms:0,arrival_vinf_kms:7,duration_years:2.7,max_vinf_mismatch_mps:0},segments:[{start_jd:2460000,end_jd:2461000,r:[1e8,0,0],v:[0,30,0]}],id:'a'.repeat(64)});
const document=()=>({schema_version:1,source:source(),validation:{numerical_validation_passed:true,clearance_screen_passed:true,export_kind:'planet',exported_launch_c3_km2_s2:11,total_onboard_delta_v_kms:.01,patch_join_delta_v_kms:.01},states:[[2460000,1e8,0,0,0,30,0],[2461000,2e8,1e8,0,0,15,0]],burns:[{kind:'finite_patch_junction',julian_date_tdb:2460500,magnitude_kms:.01,dx_kms:.01,dy_kms:0,dz_kms:0}]});
class Bucket{objects=new Map();async head(k){return this.objects.get(k)||null}async put(k,bytes,meta){this.objects.set(k,{key:k,bytes,customMetadata:meta.customMetadata})}async list({prefix}){return {objects:[...this.objects.values()].filter(o=>o.key.startsWith(prefix)),truncated:false}}async get(k){const o=this.objects.get(k);return o?{body:new Blob([o.bytes]).stream()}:null}}
const gzip=async d=>new Response(new Blob([JSON.stringify(d)]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();
test('exports reject unverified clearance, extra private fields and nonfinite or unordered states',async()=>{
 for(const mutate of [d=>d.validation.clearance_screen_passed=false,d=>d.log='private',d=>d.validation.cache='C:\\Users\\private',d=>d.states[1][0]=d.states[0][0],d=>d.states[1][1]=NaN,d=>d.burns[0].kind='=SUM(1)']){const d=document();mutate(d);await assert.rejects(()=>checkExport(d,validate));}
});
test('disabled storage leaves API healthy, with a clear pending upload response',async()=>{
 const env=localEnv();try{const r=await worker.fetch(new Request('https://example.test/v1/exports?candidate='+'a'.repeat(64)),env);assert.equal((await r.json()).storage_ready,false);const p=await worker.fetch(new Request('https://example.test/v1/exports',{method:'POST',body:'x'}),env);assert.equal(p.status,503);}finally{env.database.close()}
});
test('numeric export round trip preserves states, burn costs, source identity and deduplication',async()=>{
 const env=localEnv();env.EXPORTS=new Bucket();try{
  const d=document(),record=await validate(d.source);d.source=record;
  await worker.fetch(new Request('https://example.test/v1/candidates',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidates:[record]})}),env);
  const upload=()=>worker.fetch(new Request('https://example.test/v1/exports',{method:'POST',headers:{'Content-Type':'application/gzip'},body:new Uint8Array()}),env);
  const bytes=await gzip(d),request=()=>new Request('https://example.test/v1/exports',{method:'POST',headers:{'Content-Type':'application/gzip'},body:bytes});
  const first=await worker.fetch(request(),env),saved=await first.json();assert.equal(first.status,200);assert.equal(saved.candidate_id,record.id);assert.equal((await(await worker.fetch(request(),env)).json()).duplicate,true);assert.equal(env.EXPORTS.objects.size,1);
  const listing=await(await worker.fetch(new Request('https://example.test/v1/exports?candidate='+record.id),env)).json();assert.equal(listing.exports[0].rows,2);assert.equal(listing.exports[0].total_onboard_delta_v_kms,.01);
  const url='https://example.test/v1/exports/'+saved.group_id+'/'+saved.export_id;
  const file=await worker.fetch(new Request(url+'/trajectory.xyzv'),env);assert.match(file.headers.get('Content-Disposition'),/attachment/);const rows=(await file.text()).trim().split('\n').map(r=>r.split(' ').map(Number));assert.deepEqual(rows,d.states);
  const report=await(await worker.fetch(new Request(url+'/validation.json'),env)).json();assert.equal(report.source_id,record.id);assert.equal(report.validation.patch_join_delta_v_kms,.01);
  const replacement=structuredClone(record);replacement.dates_jd_tdb[0]+=.001;replacement.metrics.launch_c3_km2_s2=10;const newer=await validate(replacement);
  await worker.fetch(new Request('https://example.test/v1/candidates',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidates:[newer]})}),env);
  const retained=await(await worker.fetch(new Request('https://example.test/v1/exports?candidate='+newer.id),env)).json();assert.equal(retained.exports.length,1,'Replacing a same-day candidate must not orphan integrated downloads');
 }finally{env.database.close()}
});
