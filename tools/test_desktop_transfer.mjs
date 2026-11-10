import vm from 'node:vm';
import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {transferDocument,finiteRadiusDownload} from '../docs/desktop_transfer.js';
import {historicalMatch} from '../docs/historical_labels.js';
const root=new URL('../docs/',import.meta.url),load=p=>JSON.parse(fs.readFileSync(new URL(p,root),'utf8'));

test('desktop handoff enables explicit powered burns without counting DSMs twice',()=>{
 const c={id:'powered',c3:20,years:3,vinf:8,sequence:'EJ',bodies:['Earth','Jupiter'],events:[{jd:2460000},{jd:2461000}],burns_mps:200,burns:[{kind:'DSM',magnitude_mps:100}],community_record:{sequence:'EJ',dates_jd_tdb:[2460000,2461000],dsm_controls:[],branches:[[0,true]]}};
 assert.equal(transferDocument(c).settings.powered_flybys,true);
 c.burns_mps=100;assert.equal(transferDocument(c).settings.powered_flybys,false);
 c.powered_flybys=true;assert.equal(transferDocument(c).settings.powered_flybys,true);
});
test('every curated Lambert handoff preserves saved dates, branches and physical DSM controls',()=>{
 const catalog=load('data/index.json');let count=0;
 for(const row of catalog.cases){
  const c=load('data/cases/'+row.id+'.json');if(c.model!=='Lambert candidate')continue;
  c.desktop_record=load(c.desktop_record_url);const d=transferDocument(c,'Selected mission');
  assert.equal(d.format,'rolamgas-search-options');assert.deepEqual(d.trajectory.segments,c.desktop_record.segments);assert.deepEqual(d.trajectory.dsm_controls,c.desktop_record.dsm_controls);assert.equal(d.settings.event_windows.length,c.events.length);
  assert.deepEqual(d.settings.route_overrides[d.trajectory.sequence].branch_options,c.desktop_record.branches.map(b=>[b]));
  assert.equal(d.settings.launch_start,d.settings.launch_end);assert.equal(d.display_name,'Selected mission');assert.ok(d.settings.max_c3>=c.c3);
  if(!['Mercury','Venus','Earth','Mars','Jupiter','Saturn','Uranus','Neptune'].includes(c.target))assert.equal(String(d.settings.target_object.id),c.desktop_record.body_ids.at(-1));
  count++;
 }assert.equal(count,catalog.cases.filter(c=>c.model==='Lambert candidate').length);assert.ok(count>=91);
});
test('integrated concepts retain direct downloads and export only honest search settings',()=>{
 const c=load('data/cases/claudius-uop-2045.json'),d=transferDocument(c);assert.ok(finiteRadiusDownload(c));assert.equal(d.trajectory,undefined);assert.equal(d.settings.event_windows,undefined);
 assert.equal(finiteRadiusDownload({model:'Lambert candidate',trajectory_files:{xyzv:'unsafe.xyzv'}}),false);
});
const profiles=load('data/historical_labels.json').missions;
const jd=date=>Date.parse(date+'T12:00:00Z')/86400000+2440587.5;
test('historical names require all ordered encounter days, not a similar shape or launch',()=>{
 const m=profiles.find(m=>m.name==='Cassini'),c={bodies:m.bodies,events:m.dates.map(date=>({jd:jd(date)}))};
 assert.equal(historicalMatch(c,profiles).name,'Cassini');c.events.at(-1).jd+=365;assert.equal(historicalMatch(c,profiles),null);
 c.events.at(-1).jd-=365;c.events[2].jd+=1;assert.equal(historicalMatch(c,profiles),null);
 assert.equal(historicalMatch(load('data/cases/4fed974cbffb.json'),profiles),null);
});
test('record-based historical names remain explicitly schedule-only, planned cases distinguished',()=>{
 const m=profiles.find(m=>m.name==='Europa Clipper');const ids={Earth:'399',Mars:'499',Jupiter:'599'};
 const match=historicalMatch({body_ids:m.bodies.map(b=>ids[b]),dates_jd_tdb:m.dates.map(jd)},profiles);assert.equal(match.planned,true);assert.match(match.label,/planned-date/);
});
test('verification content matches the exact Search Console HTML file token',()=>assert.equal(fs.readFileSync(new URL('google405636ec44a3d600.html',root),'utf8').trim(),'google-site-verification: google405636ec44a3d600.html'));

test('identified mission labels are explicit recreations and selected shared missions ship in the static archive',()=>{
 const annotations=load('data/mission_annotations.json').missions,archive=load('data/community_seed_catalog.json').candidates;
 const juno='8ea27f8c3842a8a9b17a91aed85cfd74c6c55c6052e8a480c0a07a45330f0aca',near='f768b32a4c2d1122865aa5e7c7a284c498588ff1772e21de9a9634d3d9da76e2';
 assert.match(annotations[juno].label,/Juno recreation/);assert.ok(archive.some(r=>r.id===juno));assert.match(annotations['6ef2b7edc240'].label,/Dragonfly/);
 assert.match(annotations[near].label,/near match/);assert.match(annotations[near].note,/two calendar days/);assert.match(annotations['claudius-uop-2045'].label,/CLAUDIUS/);
 for(const id of [juno,near,'6ef2b7edc240'])assert.ok(annotations[id].featured_priority>0);
 const app=fs.readFileSync(new URL('../docs/app.js',import.meta.url),'utf8');assert.ok(app.indexOf('(b.featured_priority || 0)')<app.indexOf('Number(b.spotlight)'));
});

test('destination switches reset restrictive limits and mirrored year inputs',()=>{
 const app=fs.readFileSync(new URL('../docs/app.js',import.meta.url),'utf8'),start=app.indexOf('function resetDestinationFilters(){'),end=app.indexOf("$('clear-filters')",start),source=app.slice(start,end);
 const ids=['search','max-c3','max-vinf','max-burns','max-years','launch-year-min','launch-year-max','chart-launch-year-min','chart-launch-year-max','include-yellow','sort'];
 const elements=Object.fromEntries(ids.map(id=>[id,{value:'restrictive',checked:false}]));
 const ctx=vm.createContext({$:(id)=>elements[id],syncGraphYears(){for(const suffix of ['min','max'])elements['chart-launch-year-'+suffix].value=elements['launch-year-'+suffix].value;}});
 vm.runInContext('let visibleCount=999;'+source+'resetDestinationFilters()',ctx);
 for(const id of ids.slice(0,9))assert.equal(elements[id].value,'');
 assert.equal(elements['include-yellow'].checked,true);assert.equal(elements.sort.value,'recommended');
 assert.match(app,/destination!==b.dataset.target.*resetDestinationFilters/);assert.match(app,/smallBodyTarget!==b.dataset.smallBody.*resetDestinationFilters/);
});
