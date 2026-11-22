import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import '../mission_metrics.js';
import {bodyName,registerBodyNames,numberedBodyLabel,matchesBodyLabel} from '../docs/community.js';
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
 assert.equal(bodyName('20999999'),'Minor planet (999999) · name pending');
});

test('minor planets show official names before their catalogue numbers, with exact IDs',()=>{
 const names=JSON.parse(fs.readFileSync(new URL('../docs/data/body_names.json',import.meta.url),'utf8'));registerBodyNames(names);
 assert.equal(bodyName('20001036'),'Ganymed (1036)');assert.equal(bodyName('20145452'),'Ritona (145452)');assert.equal(bodyName('20055576'),'Amycus (55576)');
 registerBodyNames({bodies:{'20999998':{horizons_id:'20999998',name:'999998 (2020 AB1)'},'20999997':{horizons_id:'20001036',name:'wrong identity'}}});
 assert.equal(bodyName('20999998'),'2020 AB1 (999998)');assert.match(bodyName('20999997'),/name pending/);
 assert.notEqual(bodyName('503'),bodyName('20001036'));
 assert.equal(numberedBodyLabel('(2014 PN70)','50713036'),'2014 PN70');
 assert.equal(matchesBodyLabel('20001036','Asteroid 1036'),true);assert.equal(matchesBodyLabel('20001036','1036 Ganymed'),true);assert.equal(matchesBodyLabel('20001036','1036'),true);
 assert.equal(matchesBodyLabel('20001036','55576'),false);
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
 const vehicle={vehicle:'Model',source_label:'Synthetic model fixture',data_kind:'third_party_model',query_grid_c3:[0,10,20,28,40],points:[[0,1000],[10,500],[20,0],[28,0]],confidence95_points:[[0,500,2000],[10,0,1500],[20,0,900],[28,0,400]]};
 const d={queries:[{c3:0},{c3:6.25},{c3:10},{c3:20}],vehicles:[vehicle,{vehicle:'Study point',query_grid_c3:[30],points:[[30,3000]]}]};
 const interpolated=m.launchCapacities(d,5)[0];assert.equal(interpolated.capacity_kg,750);assert.match(m.launchCapacitySource(interpolated),/at bracket samples/);assert.match(m.launchCapacitySource(interpolated),/C3 10 → 0–1500 kg/);
 const zero=m.launchCapacities(d,28)[0];assert.equal(zero.capacity_kg,0);assert.match(m.launchCapacitySource(zero),/C3 28 → 0–400 kg/);assert.doesNotMatch(m.launchCapacitySource(zero),/C3 20/);
 assert.equal(m.launchCapacities(d,30)[0].capacity_kg,null);assert.equal(m.launchCapacities(d,29.99)[1].capacity_kg,null);assert.equal(m.launchCapacities(d,30)[1].capacity_kg,3000);
});

test('capacity datasets retain authorized model outputs separately from published references',()=>{
 for(const path of ['../docs/data/launch_performance_curves.json','../gui_assets/launch_performance_curves.json','../docs/data/international_launch_performance.json','../gui_assets/international_launch_performance.json']){
  const data=JSON.parse(fs.readFileSync(new URL(path,import.meta.url),'utf8'));
  assert.ok(data.vehicles.length>=4);
  assert.ok(!data.vehicles.some(v=>v.data_kind==='third_party_model'));
  assert.equal(data.vehicles.filter(v=>v.silverbird_id).length,path.includes('international_launch_performance.json')?0:17);
 }
});

test('single launch reference points show their actual coverage without implying zero payload',()=>{
 const data=JSON.parse(fs.readFileSync(new URL('../docs/data/launch_performance_curves.json',import.meta.url),'utf8'));
 const lm5=m.launchCapacities(data,28).find(r=>r.international_id==='wang2025_lm5_point');
 assert.ok(lm5.capacity_kg>3000);assert.equal(lm5.extrapolated,true);
 assert.match(m.launchCapacityCoverage(lm5),/Model C3 0–200/);
 assert.equal(m.launchCapacities(data,30).find(r=>r.international_id===lm5.international_id).capacity_kg,3000);
 for(const [id,mass] of [['ariane62_manual2021',2600],['ariane64_manual2021',6900]]){
  assert.equal(m.launchCapacities(data,6.25).find(r=>r.published_id===id).capacity_kg,mass);
  const extrapolated=m.launchCapacities(data,6.26).find(r=>r.published_id===id);assert.equal(extrapolated.extrapolated,true);assert.ok(extrapolated.capacity_kg<mass);
 }
});

test('SLS high-energy estimates retain their concept configuration and never extend the study curve',()=>{
 const data=JSON.parse(fs.readFileSync(new URL('../docs/data/launch_performance_curves.json',import.meta.url),'utf8'));
 const id='nasa2020_sls_block2_centaur',row=m.launchCapacities(data,158).find(r=>r.published_id===id);
 assert.equal(row.capacity_kg,5600);assert.match(row.vehicle,/Block 2 \+ Centaur.*2020 concept/);
 assert.match(row.ground_rules,/unflown/);assert.match(row.ground_rules,/28.5/);assert.match(row.source_url,/ntrs.nasa.gov/);
 assert.equal(m.launchCapacities(data,59.9).find(r=>r.published_id===id).extrapolated,true);
 assert.equal(m.launchCapacities(data,280.1).find(r=>r.published_id===id).capacity_kg,null);
 assert.ok(!data.vehicles.some(r=>/Atlas V/i.test(r.vehicle)));
 assert.deepEqual(data,JSON.parse(fs.readFileSync(new URL('../gui_assets/launch_performance_curves.json',import.meta.url),'utf8')));
 assert.equal(fs.readFileSync(new URL('../mission_metrics.js',import.meta.url),'utf8'),fs.readFileSync(new URL('../docs/mission_metrics.js',import.meta.url),'utf8'));
});

test('LVM3 estimate is labeled, rounded and restricted to its modeled range',()=>{
 const data=JSON.parse(fs.readFileSync(new URL('../docs/data/launch_performance_curves.json',import.meta.url),'utf8'));
 const at=c=>m.launchCapacities(data,c).find(r=>r.international_id==='nsil2025_lvm3_estimate');
 assert.match(at(10).source_label,/Estimated/);
 assert.match(at(10).ground_rules,/extrapolated/);
 assert.match(m.launchCapacityValue(at(10)),/1,700/);
 assert.match(m.launchCapacityValue(at(15)),/1,400/);
 assert.equal(at(30.01).extrapolated,true);
 assert.equal(at(200).capacity_kg,0);
 assert.equal(at(200.01).capacity_kg,null);
 assert.equal(at(-.01),undefined);
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


test('country selector filters the same capacity estimates and preserves multinational launchers',()=>{
 const data=JSON.parse(fs.readFileSync(new URL('../gui_assets/launch_performance_curves.json',import.meta.url)));
 const rows=m.launchCapacities(data,12);
 assert.deepEqual(m.launchCountryOptions(data),['USA','China','India','Europe','Russia','Japan','New Zealand']);
 for(const country of m.launchCountryOptions(data)){
  const selected=m.filterLaunchCountry(rows,country);assert.ok(selected.length);
  assert.ok(selected.every(v=>m.launchVehicleCountries(v).includes(country)));
 }
 assert.deepEqual(m.filterLaunchCountry(rows,'all'),rows);
 assert.ok(m.filterLaunchCountry(rows,'India').some(v=>v.silverbird_id==='lvm3'));
 assert.equal(m.filterLaunchCountry(rows,'New Zealand').length,1);
 assert.equal(m.filterLaunchCountry(rows,'unknown').length,0);
 const electron=m.filterLaunchCountry(rows,'New Zealand')[0];assert.ok(m.filterLaunchCountry(rows,'USA').includes(electron));
 assert.deepEqual(m.launchVehicleCountries({vehicle:'Falcon Heavy + STAR 48BV',parent_vehicle:'Falcon Heavy'}),['USA']);
});

test('SilverBird samples retain model intervals, interpolate only adjacent samples and never extrapolate',()=>{
 const data=JSON.parse(fs.readFileSync(new URL('../gui_assets/launch_performance_curves.json',import.meta.url)));
 const reference=data.vehicles.find(v=>v.silverbird_id==='lvm3');
 const table={vehicles:[reference]};
 const exact=m.launchCapacities(table,10)[0],between=m.launchCapacities(table,12.5)[0];
 assert.equal(exact.capacity_kg,new Map(reference.points).get(10));assert.equal(exact.interpolated,false);
 assert.equal(between.capacity_kg,(new Map(reference.points).get(10)+new Map(reference.points).get(15))/2);
 assert.match(m.launchCapacitySource(exact),/95% model interval/);
 assert.match(m.launchCapacitySource(between),/bracket samples/);
 assert.equal(m.launchCapacities(table,201)[0].capacity_kg,null);
 const gap={...reference,points:reference.points.filter(p=>p[0]!==10)};
 assert.equal(m.launchCapacities({vehicles:[gap]},12)[0].capacity_kg,null);
 const zero=m.launchCapacities(table,200)[0];assert.equal(m.launchCapacityValue(zero),'0 (model)');
 assert.equal(fs.readFileSync(new URL('../mission_metrics.js',import.meta.url),'utf8'),fs.readFileSync(new URL('../docs/mission_metrics.js',import.meta.url),'utf8'));
});
