import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {transferDocument,finiteRadiusDownload} from '../docs/desktop_transfer.js';
import {historicalMatch} from '../docs/historical_labels.js';
const root=new URL('../docs/',import.meta.url),load=p=>JSON.parse(fs.readFileSync(new URL(p,root),'utf8'));
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
 }assert.equal(count,91);
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
