import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import '../launch_energy_review.js';
const r=LaunchEnergyReview;
const row=(id,c3,years,sequence='EdvEJ',target='599')=>({id,sequence,body_ids:['399','399',target],metrics:{launch_c3_km2_s2:c3,duration_years:years}});
test('same complete sequence and target are isolated despite sharing the departure leg',()=>{
 const reference=r.build([row('a',28,6),row('b',30,7),row('c',90,9,'EdvES','699')]);
 assert.equal(Object.keys(reference.groups).length,2);assert.equal(r.firstLeg('EdvEJ'),'EdvE');assert.equal(r.firstLeg('EVdvEEJ'),'EV');
});
test('an expensive statistical outlier turns yellow only without a meaningful time advantage',()=>{
 const ref=r.build(Array.from({length:10},(_,i)=>row(String(i),27+i/2,6+i/20)));
 const ordinary=r.review(row('new',33,6),ref);assert.equal(ordinary.flagged,false);
 const costly=r.review(row('new',130,6),ref);assert.equal(costly.flagged,true);assert.ok(costly.witness);assert.equal(costly.statistics.n,10);
 assert.equal(r.review(row('fast',180,3),ref).flagged,false);
 assert.equal(r.review(row('unknown',180,6,'EdvES','699'),ref).flagged,false);
});
test('both reported examples receive review labels against the saved library',()=>{
 const ref=JSON.parse(fs.readFileSync(new URL('../docs/data/launch_energy_reference.json',import.meta.url),'utf8'));
 const chiron=row('27ddb0bce491f4de537b40dc597c26306b35697c429367cf146ce2795c31e088',133.5952318236,15.496032,'EdvEJX','20002060');
 const venus={...row('44300dde9f5cd7dea61b6e907f72f8d068af193e982755d1185a079294f3d346',199.98687775,.93626958,'EMV','299'),body_ids:['399','499','299']};
 assert.equal(r.review(chiron,ref).flagged,true);assert.equal(r.review(venus,ref).flagged,true);
});
test('a batch notice needs several high-energy multigravity-assist candidates',()=>{
 assert.equal(r.notice([row('a',160,5)]).show,false);assert.equal(r.notice([row('a',160,5),row('b',170,6),row('c',180,7)]).show,true);
});
test('entry advisories distinguish absolute energy, relative energy and missing comparisons',()=>{
 const ref=JSON.parse(fs.readFileSync(new URL('../docs/data/launch_energy_reference.json',import.meta.url),'utf8'));
 const venus={id:'9df1198af24d8064f1097c3fedc55b4beab1cdeabf5a298f790790d4e91ea3b4',sequence:'EV',body_ids:['399','299'],metrics:{launch_c3_km2_s2:122.927958964,duration_years:.246406571}};
 const advisory=r.review(venus,ref);assert.equal(advisory.energy_level,'extreme');assert.match(advisory.energy_label,/RIDICULOUSLY HIGH/);assert.ok(advisory.statistics.median<20);
 assert.equal(r.review({...venus,metrics:{launch_c3_km2_s2:16,duration_years:.5}},ref).energy_level,'usual');
 assert.equal(r.review(row('unknown',110,6,'UNSEEN','999'),ref).energy_level,'high');
 assert.equal(r.review(row('unknown',180,3,'UNSEEN','999'),ref).energy_level,'extreme');
 assert.equal(r.review(row('unknown',20,3,'UNSEEN','999'),ref).energy_level,'unrated');
 const fast=r.review(row('fast',180,3),r.build(Array.from({length:5},(_,i)=>row(String(i),28,6))));
 assert.equal(fast.energy_level,'extreme');assert.equal(fast.flagged,false);
});
