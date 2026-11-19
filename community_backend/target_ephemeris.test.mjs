import test from 'node:test';import assert from 'node:assert/strict';
import {parseVectors,targetEphemeris} from './target_ephemeris.mjs';
const header='Target body name: Pluto (999)\nCenter body name: Sun (10)\nGEOMETRIC cartesian states\nEcliptic of J2000.0\nOutput units : AU-D\nJDTDB,Calendar Date\n';
const text=header+'$$SOE\n2462502.5,date,30,0,0,0,.003,0,\n2462503.5,date,30,.003,0,0,.003,0,\n$$EOE';
test('JPL target vectors require identity, geometric frame, units and ordered finite states',()=>{
 assert.equal(parseVectors(text,'999','Pluto').length,2);
 for(const bad of [text.replace('AU-D','KM-S'),text.replace('Sun (10)','Earth (399)'),text.replace('30,.003','bad,.003'),text.replace('2462503.5','2462502.5')])assert.throws(()=>parseVectors(bad,'999','Pluto'));
 assert.throws(()=>parseVectors(text,'1','Ceres'));
});
test('only known public targets fetch JPL; repeated requests use shared cache',async()=>{
 const slots=new Map(),calls=[],cache={match:async r=>slots.get(r.url)?.clone(),put:async(r,v)=>slots.set(r.url,v)},env={DB:{prepare:()=>({bind:()=>({first:async()=>({present:1})})})}};
 const fetcher=async url=>{calls.push(url);return Response.json(url.includes('lookup')?{result:[{spkid:'999',name:'Pluto',type:'planet'}]}:{result:text})};
 const request=new Request('https://example.org/v1/target-vectors?target=999&block=2030');
 const result=await targetEphemeris(request,env,null,fetcher,cache),data=await result.json();
 assert.equal(data.target_id,'999');assert.equal(data.units,'AU and AU/day');assert.equal(calls.length,2);
 const again=await targetEphemeris(request,env,null,fetcher,cache);assert.equal(again.status,200);assert.equal(calls.length,2);
 await assert.rejects(targetEphemeris(new Request('https://example.org/?target=999&block=2033'),env,null,fetcher,cache));
 const unknown={DB:{prepare:()=>({bind:()=>({first:async()=>null})})}};
 assert.equal((await targetEphemeris(new Request('https://example.org/?target=12345&block=2030'),unknown,null,fetcher,cache)).status,404);
 assert.equal(calls.length,2);
});
