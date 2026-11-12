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
test('mission limits and graph mode round-trip in deep links without accepting invalid numbers',()=>{const hash=withMissionFilters('#target=Jupiter&mission=4d76acaf1f6f',{metric:'vinf',maxYears:'8',maxC3:'40',maxVinf:'12',maxBurns:'700'});assert.deepEqual(missionFiltersFromHash(hash),{metric:'vinf',maxYears:'8',maxC3:'40',maxVinf:'12',maxBurns:'700'});assert.equal(missionFiltersFromHash('#axis=bad&max_years=NaN&max_c3=-1').maxC3,'');assert.equal(missionFiltersFromHash('#axis=bad').metric,'c3')});

test('planet playback shares the stored spacecraft encounter dates, axes and distance units',()=>{
 const table=JSON.parse(fs.readFileSync(new URL('../docs/data/planet_playback.json',import.meta.url),'utf8'));
 const c=JSON.parse(fs.readFileSync(new URL('../docs/data/cases/4d76acaf1f6f.json',import.meta.url),'utf8'));
 for(const event of c.events){const segment=table.bodies[event.body].segments.find(s=>s.start<=event.jd&&event.jd<=s.end);const p=m.ephemerisPosition(segment,event.jd);assert.ok(p,'Coverage for '+event.body);const error=Math.hypot(...p.map((v,i)=>v-event.position_au[i]))*149597870.7;assert.ok(error<2000,`${event.body} display ephemeris error ${error} km`);}
});

test('hide coast corrections that round to zero without hiding real burns or altering totals',()=>{
 const burns=[{kind:'Coast 2 targeting correction',magnitude_mps:0},{kind:'Coast 3 targeting correction',magnitude_mps:.0049},{kind:'Coast 4 targeting correction',magnitude_mps:.005},{kind:'DSM',magnitude_mps:0},{kind:'powered flyby',magnitude_mps:50}];
 assert.deepEqual(burns.filter(m.visibleManeuver),burns.slice(2));assert.equal(burns.length,5);assert.equal(m.visibleManeuver({kind:'Coast 2 targeting correction',magnitude_kms:1e-8}),false);
});
test('NASA capacities retain configuration, interpolate only inside known adjacent samples and never extrapolate',()=>{
 const d={queries:[{c3:0},{c3:10},{c3:20}],vehicles:[{vehicle:'Falcon Heavy (Recovery)',points:[[0,5000],[10,3000]]},{vehicle:'Falcon Heavy (Expendable)',points:[[0,12000],[10,9000],[20,7000]]},{vehicle:'Unavailable gap',points:[[0,100],[20,80]]}]};
 const r=m.launchCapacities(d,5);assert.equal(r[0].capacity_kg,4000);assert.equal(r[1].capacity_kg,10500);assert.equal(r[2].capacity_kg,null);
 assert.equal(m.launchCapacities(d,15)[0].capacity_kg,null);assert.equal(m.launchCapacities(d,25)[1].capacity_kg,null);assert.equal(m.launchCapacities(d,10)[0].interpolated,false);
});

test('launch displays exclude VC0 and Falcon 9 RTLS while retaining other configurations',()=>{
 const names=['Vulcan (VC0)','Falcon 9 (Full Thrust, RTLS )','Vulcan (VC2)','Falcon 9 (Full Thrust, ASDS)','Falcon Heavy (Recovery)'];
 const d={queries:[{c3:10}],vehicles:names.map(vehicle=>({vehicle,points:[[10,1000]]}))};
 assert.deepEqual(m.launchCapacities(d,10).map(r=>r.vehicle),names.slice(2));
 assert.equal(m.visibleLaunchVehicle({vehicle:'Falcon 9 (Full Thrust, RTLS)'}),false);
});

test('international launchers use independent grids, never extrapolate a study point, and retain source uncertainty',()=>{
 const vehicle={vehicle:'Model',source_label:'SilverBird estimate',data_kind:'third_party_model',query_grid_c3:[0,10,20,28,40],points:[[0,1000],[10,500],[20,0],[28,0]],confidence95_points:[[0,500,2000],[10,0,1500],[20,0,900],[28,0,400]]};
 const d={queries:[{c3:0},{c3:6.25},{c3:10},{c3:20}],vehicles:[vehicle,{vehicle:'Study point',query_grid_c3:[30],points:[[30,3000]]}]};
 const interpolated=m.launchCapacities(d,5)[0];assert.equal(interpolated.capacity_kg,750);assert.match(m.launchCapacitySource(interpolated),/at bracket samples/);assert.match(m.launchCapacitySource(interpolated),/C3 10 → 0–1500 kg/);
 const zero=m.launchCapacities(d,28)[0];assert.equal(zero.capacity_kg,0);assert.match(m.launchCapacitySource(zero),/C3 28 → 0–400 kg/);assert.doesNotMatch(m.launchCapacitySource(zero),/C3 20/);
 assert.equal(m.launchCapacities(d,30)[0].capacity_kg,null);assert.equal(m.launchCapacities(d,29.99)[1].capacity_kg,null);assert.equal(m.launchCapacities(d,30)[1].capacity_kg,3000);
});

test('historical missions have continuous playback coverage for every visited planet',()=>{
 const table=JSON.parse(fs.readFileSync(new URL('../docs/data/planet_playback.json',import.meta.url),'utf8'));
 const profiles=JSON.parse(fs.readFileSync(new URL('../docs/data/historical_labels.json',import.meta.url),'utf8')).missions;
 for(const mission of profiles){
  const lo=Date.parse(mission.dates[0]+'T00:00:00Z')/86400000+2440587.5,hi=Date.parse(mission.dates.at(-1)+'T00:00:00Z')/86400000+2440587.5;
  for(const body of new Set(mission.bodies))if(table.bodies[body]){
   const segment=table.bodies[body].segments.find(s=>s.start<=lo&&hi<=s.end);
   assert.ok(segment,mission.name+' '+body+' continuous playback interval');
   assert.ok(m.ephemerisPosition(segment,lo));assert.ok(m.ephemerisPosition(segment,hi));
  }
 }
});
