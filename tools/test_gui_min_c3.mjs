import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../gui.js',import.meta.url),'utf8').split("$('reuse').onclick=")[0];
function gui(){
 const elements={showYellow:{checked:true},showRed:{checked:true},onlyPins:{checked:false},routeFilter:{value:''},sort:{value:'launch_c3_km2_s2'},minC3:{value:'999'}};
 const context=vm.createContext({document:{getElementById:id=>elements[id]}});
 vm.runInContext(source,context);
 return {elements,run:code=>vm.runInContext(code,context)};
}
const rows=JSON.stringify([
 {id:'below',status:'near_miss_not_accepted',launch_c3_km2_s2:137.88,sequence:'EJX',max_vinf_mismatch_mps:0},
 {id:'passing',status:'passes_configured_patched_conic_screen',launch_c3_km2_s2:150,sequence:'EJX',max_vinf_mismatch_mps:0},
 {id:'yellow',status:'near_miss_not_accepted',launch_c3_km2_s2:155,sequence:'EJX',max_vinf_mismatch_mps:0},
 {id:'red',status:'near_miss_not_accepted',launch_c3_km2_s2:165,sequence:'EJX',max_vinf_mismatch_mps:2500}
]);
function setup(){const g=gui();g.run(`state.limits={min_c3:150,max_single_dsm_kms:.7};state.rows=${rows}`);return g;}
test('minimum applies even with both yellow and red included',()=>{
 const g=setup();assert.equal(g.run('filtered().map(q=>q.id).join(",")'),'passing,yellow,red');
 assert.equal(g.run('failedLimits(state.rows[0]).includes("C3 below minimum 150")'),true);
});
test('below-minimum diagnostics are always excluded from the gallery',()=>{
 const g=setup();
 assert.equal(g.run('filtered().map(q=>q.id).join(",")'),'passing,yellow,red');
 assert.equal(g.run('severity(state.rows[0])'),'warning');
 g.run('state.rows[0].status="passes_configured_patched_conic_screen"');
 assert.equal(g.run('severity(state.rows[0])'),'warning');
});
test('other diagnostic filters still work above the C3 floor',()=>{
 const g=setup();g.elements.showYellow.checked=false;
 assert.equal(g.run('filtered().map(q=>q.id).join(",")'),'passing,red');
});
test('the saved run limit is authoritative, not an unsaved form edit',()=>{
 const g=setup();assert.equal(g.run('filtered().map(q=>q.id).join(",")'),'passing,yellow,red');
 g.run('state.limits={};state.rows[0].launch_c3_km2_s2=0');
 assert.equal(g.run('filtered().length'),3);
});
test('absolute floor survives missing or zero legacy run limits',()=>{
 const g=setup();
 for(const limits of ['{}','{min_c3:0}','{min_c3:0,effective_min_c3:0}']){
  g.run(`state.limits=${limits}`);
  for(const energy of [0,4.99,4.999999999])assert.equal(g.run(`belowC3Minimum({launch_c3_km2_s2:${energy}})`),true);
  assert.equal(g.run('belowC3Minimum({launch_c3_km2_s2:5})'),false);
 }
});
test('boundary tolerance agrees with solver acceptance',()=>{
 const g=setup();g.run('state.rows[0].launch_c3_km2_s2=150-1e-10');
 assert.equal(g.run('belowC3Minimum(state.rows[0])'),false);
 g.run('state.rows[0].launch_c3_km2_s2=150-1e-6');
 assert.equal(g.run('belowC3Minimum(state.rows[0])'),true);
});

test('unresolved speed joins never present a zero complete burn budget',()=>{
 const g=gui();
 assert.equal(g.run('maneuverText({total_dsm_kms:0,max_vinf_mismatch_mps:2500},2)'),'Unresolved');
 assert.equal(g.run('maneuverText({total_dsm_kms:.4,maneuver_budget_complete:false,max_vinf_mismatch_mps:101},2)'),'0.40 + ?');
 assert.equal(g.run('maneuverText({total_dsm_kms:.15,maneuver_budget_complete:true,max_vinf_mismatch_mps:2000},2)'),'0.15');
});
test('effective search floor overrides a legacy zero requested minimum',()=>{
 const g=setup();g.run('state.limits={min_c3:0,effective_min_c3:6.25};state.rows[0].launch_c3_km2_s2=0');
 assert.equal(g.run('belowC3Minimum(state.rows[0])'),true);
});

test('unresolved display uses a strict 100 m/s threshold',()=>{
 const g=gui();
 for(const value of [0,.001,20,99.999,100])assert.equal(g.run(`maneuverText({total_dsm_kms:0,maneuver_budget_complete:false,max_vinf_mismatch_mps:${value}},2)`),'0.00');
 assert.equal(g.run('maneuverText({total_dsm_kms:0,maneuver_budget_complete:false,max_vinf_mismatch_mps:100.001},2)'),'Unresolved');
 assert.equal(g.run('maneuverText({total_dsm_kms:.25,max_unresolved_vinf_mismatch_mps:50,max_vinf_mismatch_mps:2000,maneuver_budget_complete:false},2)'),'0.25');
 assert.equal(g.run('maneuverText({total_dsm_kms:.25,flybys:[{speed_mismatch_mps:2000,passes_powered_geometry:true},{speed_mismatch_mps:50}],maneuver_budget_complete:false},2)'),'0.25');
});
test('duration uses full-epoch years and falls back to stored Julian dates',()=>{
 const g=gui();
 assert.equal(g.run('flightDuration({duration_years:2.123456789})'),'2.1235 years');
 assert.equal(g.run('flightDuration({dates_jd_tdb:[2460000.5,2460731]})'),'2.0000 years');
 assert.equal(g.run('flightDuration({duration_years:0})'),'0.0000 years');
 assert.equal(g.run('flightDuration({})'),'—');
});

test('mission profile selects its appropriate C3 starting boundary',()=>{
 const elements={missionProfile:{value:'flyby'},profileNote:{textContent:''}};
 const context=vm.createContext({document:{getElementById:id=>elements[id]??(elements[id]={value:''})}});vm.runInContext(source,context);
 vm.runInContext('applyProfile()',context);assert.equal(elements.c3SeedBoundary.value,'maximum');
 elements.missionProfile.value='orbiter';vm.runInContext('applyProfile()',context);assert.equal(elements.c3SeedBoundary.value,'minimum');
});
test('obsolete below-minimum toggle is absent and arrival-date controls are not collapsed',()=>{
 const html=fs.readFileSync(new URL('../gui.html',import.meta.url),'utf8');
 assert.equal(html.includes('id="showBelowMinC3"'),false);
 assert.ok(html.includes('Include yellow (tighten boundaries)'));assert.ok(html.includes('Include red (may be physically impossible)'));
 const prefix=html.slice(0,html.indexOf('id="arrivalDate"'));
 assert.equal((prefix.match(/<details\b/g)||[]).length,(prefix.match(/<\/details>/g)||[]).length);
});

test('gallery defaults include yellow and exclude red',()=>{const html=fs.readFileSync(new URL('../gui.html',import.meta.url),'utf8');assert.match(html,/<input[^>]*id="showYellow"[^>]*checked/);assert.doesNotMatch(html,/<input[^>]*id="showRed"[^>]*checked/)});
