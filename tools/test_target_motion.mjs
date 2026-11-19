import test from 'node:test';import assert from 'node:assert/strict';
import {targetId,targetPosition,targetMotion,loadTargetMotion} from '../docs/target_motion.js';
test('dated target data is fetched once per block and retained across mission ranges',async()=>{
 const original=globalThis.fetch,c={target:'Pluto',target_id:'999',start:2462502.5,end:2462503.5};let calls=0;
 globalThis.fetch=async url=>{calls++;const year=Number(new URL(url).searchParams.get('block')),start=2440587.5+Date.UTC(year,0,1)/86400000;return Response.json({target_id:'999',segments:[{start,end:start+3654,states:[[start,1,2,3,0,0,0],[start+3654,2,3,4,0,0,0]]}]});};
 try{
  await Promise.all([loadTargetMotion(c,'https://example.test'),loadTargetMotion(c,'https://example.test')]);assert.equal(calls,1);
  const span=targetMotion.get('999').segments[0];assert.deepEqual(targetPosition(c,'Pluto',c.start,s=>s.states[0].slice(1,4)),[1,2,3]);
  assert.equal(targetPosition(c,'Pluto',span.end+1,()=>assert.fail('Never extrapolate')),null);assert.equal(targetPosition(c,'Earth',c.start,()=>assert.fail()),null);
  const later={...c,start:2469807.5,end:2469808.5};await loadTargetMotion(later,'https://example.test');assert.equal(targetMotion.get('999').segments.length,2);
 }finally{globalThis.fetch=original;targetMotion.clear();}
});
test('unresolved objects keep the encounter fallback without requesting arbitrary URLs',async()=>{
 assert.equal(targetId({community_record:{}}),'');assert.equal(await loadTargetMotion({target:'Unknown'},'https://example.test'),null);
});
