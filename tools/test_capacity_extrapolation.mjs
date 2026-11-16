import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const context={};vm.createContext(context);vm.runInContext(fs.readFileSync(new URL('../mission_metrics.js',import.meta.url),'utf8'),context);
const m=context.MissionMetrics,data=JSON.parse(fs.readFileSync(new URL('../docs/data/launch_performance_curves.json',import.meta.url),'utf8'));
test('every listed configuration has a finite nonnegative estimate at C3 158 and 200',()=>{
 for(const c of [158,200])for(const row of m.launchCapacities(data,c)){
  assert.ok(Number.isFinite(row.capacity_kg),row.vehicle+' at '+c);assert.ok(row.capacity_kg>=0);
  assert.doesNotMatch(m.launchCapacityValue(row),/Not tabulated/);
 }
});
test('native samples take precedence over attached models',()=>{
 for(const v of data.vehicles)for(const [c,mass] of v.points){
  const row=m.launchCapacities(data,c).find(r=>r.vehicle===v.vehicle);if(!row)continue;
  assert.equal(row.capacity_kg,mass);assert.notEqual(row.extrapolated,true);
 }
});
test('extrapolated values are explicit and do not continue past 200',()=>{
 const row=m.launchCapacities(data,158).find(v=>v.vehicle==='Falcon Heavy (Expendable)');
 assert.equal(row.extrapolated,true);assert.equal(row.capacity_kg,0);assert.match(m.launchCapacitySource(row),/Extrapolated estimate/);assert.equal(m.launchCapacityValue(row),'0 (model)');
 const beyond=m.launchCapacities(data,200.001).find(v=>v.vehicle===row.vehicle);assert.equal(beyond.capacity_kg,null);
 const sls=m.launchCapacities(data,220).find(v=>v.published_id==='nasa2020_sls_block2_centaur');assert.ok(sls.capacity_kg>0);assert.notEqual(sls.extrapolated,true);
});
test('kick-stage configurations pay for motor and hardware and name their assumptions',()=>{
 const rows=m.launchCapacities(data,158);const fh=rows.find(v=>v.parent_vehicle==='Falcon Heavy (Expendable)');
 assert.ok(fh.capacity_kg>700&&fh.capacity_kg<1000);assert.equal(fh.model_parameters.motor_wet_mass_kg,2171);assert.equal(fh.model_parameters.integration_mass_kg,100);assert.equal(fh.model_parameters.assumed_kick_loss_km_s,.1);
 assert.match(fh.source_label,/not flight-qualified/);assert.match(fh.ground_rules,/no parent extrapolation/);
 assert.ok(m.launchCapacities(data,200).find(v=>v.vehicle===fh.vehicle).capacity_kg<fh.capacity_kg);
 assert.ok(!m.launchCapacities(data,20).some(v=>v.kickstage_id));
});
test('an empty exact NASA response does not hide capacity estimates',()=>{
 assert.equal(m.launchCapacities(data,158,{vehicles:[],availability:'no_vehicles_listed'}).length,m.launchCapacities(data,158).length);
 const exact={vehicle:'Falcon Heavy (Expendable)',capacity_kg:123};
 const rows=m.launchCapacities(data,158,{vehicles:[exact]});assert.equal(rows.find(r=>r.vehicle===exact.vehicle).capacity_kg,123);assert.ok(rows.some(r=>r.kickstage_id));
});
