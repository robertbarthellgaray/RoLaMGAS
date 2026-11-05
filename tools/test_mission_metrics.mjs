import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import '../mission_metrics.js';
import {bodyName,registerBodyNames} from '../docs/community.js';
const m=globalThis.MissionMetrics;
test('circular parking injection satisfies Earth hyperbolic energy and separates cruise burns',()=>{
 const p=m.parkingInjection(6.25,200,'Earth');assert.ok(Math.abs(p.deltaVKms-3.5)<.01);
 assert.ok(Math.abs(p.hyperbolicKms**2-2*398600.435436/p.radiusKm-6.25)<1e-12);
 assert.equal(p.hyperbolicKms-p.circularKms,p.deltaVKms);
 const escape=m.parkingInjection(0,200);assert.ok(Math.abs(escape.deltaVKms/escape.circularKms-(Math.sqrt(2)-1))<1e-14);
 assert.ok(m.parkingInjection(40,200).deltaVKms>p.deltaVKms);
 assert.equal(m.parkingInjection(-1,200),null);assert.equal(m.parkingInjection(10,0),null);assert.equal(m.parkingInjection(10,200,'Comet'),null);
});
test('comparison computes mean, median, population deviation and tie-aware percentile',()=>{
 const s=m.summary([10,20,30,NaN,undefined],20);assert.equal(s.n,3);assert.equal(s.mean,20);assert.equal(s.median,20);assert.ok(Math.abs(s.stddev-Math.sqrt(200/3))<1e-12);assert.equal(s.percentile,50);
 assert.equal(m.summary([20,20],20).percentile,50);assert.equal(m.summary([2,4],3).median,3);assert.equal(m.summary([],1),null);
});
test('sequence comparisons never mix targets or assist sequences',()=>{
 const selected={sequence:'EVEEJ',target:'Jupiter',c3:20,years:6,vinf:5};
 const rows=[selected,{...selected,c3:40},{...selected,sequence:'EJ',c3:500},{...selected,target:'Saturn',c3:900}];
 const s=m.compare(rows,selected);assert.equal(s.n,2);assert.equal(s.c3.mean,30);assert.equal(s.c3.percentile,25);
});
test('planet interpolation follows dated Hermite states and refuses extrapolation',()=>{
 const table={states:[[10,0,0,0,1,0,0],[12,2,4,0,1,4,0]]};assert.deepEqual(m.ephemerisPosition(table,11),[1,1,0]);assert.deepEqual(m.ephemerisPosition(table,10),[0,0,0]);assert.deepEqual(m.ephemerisPosition(table,12),[2,4,0]);assert.equal(m.ephemerisPosition(table,9.9),null);assert.equal(m.ephemerisPosition(table,12.1),null);
});
test('public labels use exact JPL identities, including the previously swapped small-body IDs',()=>{
 const names=JSON.parse(fs.readFileSync(new URL('../docs/data/body_names.json',import.meta.url),'utf8'));registerBodyNames(names);
 assert.match(bodyName('20225088'),/Gonggong/);assert.match(bodyName('20469219'),/Kamo/);assert.match(bodyName('20010253'),/Westerwald/);
 assert.equal(bodyName('54667839'),'2026 ED138');assert.equal(bodyName('50666516'),'2012 VP113');
 assert.equal(bodyName('20999999'),'Asteroid 999999');
});
test('desktop and public site use byte-identical scientific display calculations',()=>{
 assert.equal(fs.readFileSync(new URL('../mission_metrics.js',import.meta.url),'utf8'),fs.readFileSync(new URL('../docs/mission_metrics.js',import.meta.url),'utf8'));
});

import {missionFiltersFromHash,withMissionFilters} from '../docs/library_analysis.js';
test('mission limits and graph mode round-trip in deep links without accepting invalid numbers',()=>{const hash=withMissionFilters('#target=Jupiter&mission=4d76acaf1f6f',{metric:'vinf',maxYears:'8',maxC3:'40',maxVinf:'12',maxBurns:'700'});assert.deepEqual(missionFiltersFromHash(hash),{metric:'vinf',maxYears:'8',maxC3:'40',maxVinf:'12',maxBurns:'700'});assert.equal(missionFiltersFromHash('#axis=bad&max_years=NaN&max_c3=-1').maxC3,'');assert.equal(missionFiltersFromHash('#axis=bad').metric,'years')});

test('planet playback shares the stored spacecraft encounter dates, axes and distance units',()=>{
 const table=JSON.parse(fs.readFileSync(new URL('../docs/data/planet_playback.json',import.meta.url),'utf8'));
 const c=JSON.parse(fs.readFileSync(new URL('../docs/data/cases/4d76acaf1f6f.json',import.meta.url),'utf8'));
 for(const event of c.events){const segment=table.bodies[event.body].segments.find(s=>s.start<=event.jd&&event.jd<=s.end);const p=m.ephemerisPosition(segment,event.jd);assert.ok(p,'Coverage for '+event.body);const error=Math.hypot(...p.map((v,i)=>v-event.position_au[i]))*149597870.7;assert.ok(error<2000,`${event.body} display ephemeris error ${error} km`);}
});
