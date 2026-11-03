import {readFileSync} from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {position,missionTiming,mergeLibrary,state,caseFor,trajectoryText,fetchUpdates} from '../docs/community.js';
test('public gallery samples two-body arcs with correct circular geometry',()=>{const AU=149597870.7,mu=132712440041.27942,speed=Math.sqrt(mu/AU),period=2*Math.PI*Math.sqrt(AU**3/mu);const r=position([AU,0,0],[0,speed,0],period/4);assert.ok(Math.abs(r[0])<.01);assert.ok(Math.abs(r[1]-AU)<.01);});
test('public gallery handles outbound hyperbolic trajectories',()=>{const r=position([149597870.7,0,0],[0,55,1],60*365.25*86400);assert.ok(r.every(Number.isFinite));assert.ok(Math.hypot(...r)>149597870.7*100);});

test('community calendar dates and flight time come from TDB Julian epochs',()=>{
 const t=missionTiming({dates_jd_tdb:[2463232.5,2463598.5]});assert.equal(t.departure,'2032-01-01');assert.equal(t.arrival,'2033-01-01');assert.equal(t.days,366);assert.equal(t.years,366/365.25);assert.throws(()=>missionTiming({dates_jd_tdb:[2463232.5,2463232.5]}));
});
test('full archive remains browsable beyond the live API result cap',()=>{
 const rows=Array.from({length:130},(_,i)=>({id:String(i),body_ids:['399','599'],metrics:{launch_c3_km2_s2:i}})),live=[{...rows[4],received_at:'2026-11-03T00:00:00Z'}];
 assert.equal(mergeLibrary(rows,live,'599').length,130);assert.equal(mergeLibrary(rows,live,'599',4,7).length,4);assert.equal(mergeLibrary(rows,live,'299').length,0);assert.equal(mergeLibrary(rows,live,'599').find(r=>r.id==='4').received_at,live[0].received_at);
});

test('interactive playback and CSV/XYZV keep analytic two-body velocities',()=>{
 const AU=149597870.7,mu=132712440041.27942,v=Math.sqrt(mu/AU),period=2*Math.PI*Math.sqrt(AU**3/mu),[r,speed]=state([AU,0,0],[0,v,0],period/4);
 assert.ok(Math.abs(r[0])<.01);assert.ok(Math.abs(speed[0]+v)<1e-8);assert.ok(Math.abs(speed[1])<1e-8);
 const record=JSON.parse(readFileSync(new URL('../docs/data/community_seed_catalog.json',import.meta.url),'utf8')).candidates[0],c=caseFor(record);
 assert.equal(c.events.length,record.body_ids.length);assert.equal(c.paths.length,record.segments.length);
 const csv=trajectoryText(record,'csv').trim().split('\n'),rows=csv.slice(1).map(line=>line.split(',').map(Number));
 assert.equal(rows[0].length,7);assert.ok(rows.flat().every(Number.isFinite));assert.ok(rows.every((row,i)=>!i||row[0]>rows[i-1][0]));
 assert.ok(Math.abs(rows[0][0]-record.dates_jd_tdb[0])<1e-8);assert.match(trajectoryText(record,'xyzv'),/^# RoLaMGAS/);
});
test('near-parabolic archived coasts converge and conserve energy',()=>{
 const r=[-6515378.1515008705,-151861803.76125592,13228.731393472097],v=[41.178824100266155,-6.805316299827183,-2.186908979205583],mu=132712440041.27942;
 const [a,b]=state(r,v,19157384.008485932),energy=(r,v)=>v.reduce((s,x)=>s+x*x,0)/2-mu/Math.hypot(...r);
 assert.ok(a.every(Number.isFinite));assert.ok(Math.abs(energy(r,v)-energy(a,b))<1e-8);
});
test('live all-target feed follows every page and advances its watermark',async()=>{
 let calls=0;const result=await fetchUpdates('https://example.test','2026-01-01T00:00:00.000Z',async url=>{
  calls++;const q=new URL(url).searchParams;assert.equal(q.get('target'),'all');
  return {ok:true,json:async()=>({candidates:[{id:String(calls),received_at:`2026-01-0${calls+1}T00:00:00.000Z`}],next_cursor:calls===1?'cursor':null})};
 });assert.equal(calls,2);assert.equal(result.records.length,2);assert.equal(result.watermark,'2026-01-03T00:00:00.000Z');
});
