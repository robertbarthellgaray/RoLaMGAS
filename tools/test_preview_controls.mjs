import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../gui.js',import.meta.url),'utf8').split("$('reuse').onclick=")[0];
function gui(){
 const operations={arcs:[],strokes:0,labels:[]},context2d={scale(){},clearRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){operations.strokes++},arc(x,y,r){operations.arcs.push(r)},fill(){},fillText(text){operations.labels.push(text)},measureText(text){return {width:text.length*5}}};
 const elements={planetMarkers:{checked:true},planetPaths:{checked:true},detail:{open:true},plane:{value:'xy'},detailPlot:{getBoundingClientRect:()=>({width:800,height:500}),getContext:()=>context2d}};
 const context=vm.createContext({document:{getElementById:id=>elements[id]},devicePixelRatio:1});vm.runInContext(source,context);
 const run=code=>vm.runInContext(code,context);
 run(`state.limits={max_dsm_kms:1,max_single_dsm_kms:.7};state.card={status:'passes_configured_patched_conic_screen',paths:[[[1,0,0],[2,0,0]]],planet_paths:[{body:'Earth',points:[[0,1,0],[0,2,0]]}],events:[{body:'Earth',date:'2030-01-01',planet_state_km_kms:[149597870.7,0,0,0,0,0]}]}`);
 return {elements,run,operations};
}
test('planet markers and orbital paths can be toggled independently',()=>{
 const g=gui();g.elements.planetMarkers.checked=false;g.run('drawPlot()');
 assert.deepEqual(g.operations.arcs,[5]);assert.equal(g.operations.strokes,2);assert.ok(!g.operations.labels.some(v=>v.startsWith('Earth')));
 const h=gui();h.elements.planetPaths.checked=false;h.run('drawPlot()');
 assert.deepEqual(h.operations.arcs,[5,3]);assert.equal(h.operations.strokes,1);assert.ok(h.operations.labels.some(v=>v.startsWith('Earth')));
});
test('per-body visibility preserves independent orbit and marker preferences',()=>{
 const g=gui();g.run("previewHidden.orbits.add('Earth');drawPlot()");assert.deepEqual(g.operations.arcs,[5,3]);assert.equal(g.operations.strokes,1);
 g.elements.planetPaths.checked=false;assert.equal(g.run("bodyVisible('Earth','markers')"),true);g.elements.planetPaths.checked=true;assert.equal(g.run("bodyVisible('Earth','orbits')"),false);
});
test('combined unresolved flyby screening sum is red even when every individual mismatch is below cap',()=>{
 const g=gui(),q={status:'passes_configured_patched_conic_screen',total_dsm_kms:.3,max_vinf_mismatch_mps:500,flybys:[{speed_mismatch_mps:400},{speed_mismatch_mps:500}]};
 g.run('state.card='+JSON.stringify(q));assert.equal(g.run('severity(state.card)'),'failure');assert.ok(g.run('failedLimits(state.card).join(" ")').includes('Combined flyby mismatch + modeled burns'));
 q.total_dsm_kms=.1;g.run('state.card='+JSON.stringify(q));assert.equal(g.run('severity(state.card)'),'pass');
});
test('already modeled powered flybys are not counted twice in combined screening',()=>{
 const g=gui(),q={status:'passes_configured_patched_conic_screen',total_dsm_kms:.8,max_vinf_mismatch_mps:1000,flybys:[{speed_mismatch_mps:1000,passes_powered_geometry:true},{speed_mismatch_mps:200}]};
 g.run('state.card='+JSON.stringify(q));assert.equal(g.run('combinedMismatchScreen(state.card)'),1);assert.equal(g.run('severity(state.card)'),'pass');
 q.flybys[1].speed_mismatch_mps=201;g.run('state.card='+JSON.stringify(q));assert.equal(g.run('severity(state.card)'),'failure');
});
test('red diagnostics skip drawing trajectory or planet paths',()=>{
 const g=gui();g.run('state.card.modeled_plus_unresolved_mismatch_kms=2;state.card.total_unresolved_vinf_mismatch_mps=1000;drawPlot()');assert.equal(g.operations.strokes,0);assert.equal(g.operations.arcs.length,0);assert.ok(g.operations.labels.some(s=>s.includes('diagnostic preview')));
});
test('website uses the same independent global and per-body switches',()=>{
 const web=fs.readFileSync(new URL('../docs/app.js',import.meta.url),'utf8'),snippet=web.slice(web.indexOf('const previewHidden='),web.indexOf('function category(c)'));
 const elements={'planet-arcs':{checked:true},'planet-markers':{checked:true}},ctx=vm.createContext({$:(id)=>elements[id]});vm.runInContext(snippet,ctx);
 assert.equal(vm.runInContext("bodyVisible('Venus','markers')",ctx),true);elements['planet-markers'].checked=false;assert.equal(vm.runInContext("bodyVisible('Venus','markers')",ctx),false);assert.equal(vm.runInContext("bodyVisible('Venus','orbits')",ctx),true);
 vm.runInContext("previewHidden.orbits.add('Venus')",ctx);assert.equal(vm.runInContext("bodyVisible('Venus','orbits')",ctx),false);
});

test('pure modeled burn budget excess stays yellow when there is no unresolved mismatch',()=>{const g=gui();g.run("state.card.status='near_miss_not_accepted';state.card.total_dsm_kms=1.2;state.card.max_single_dsm_kms=.6;state.card.flybys=[]");assert.equal(g.run('severity(state.card)'),'warning')});

test('explicitly requested red diagnostic draws its paths while staying red',()=>{const g=gui();g.run('state.card.modeled_plus_unresolved_mismatch_kms=2;state.card.total_unresolved_vinf_mismatch_mps=1000;state.card.manual_preview=true;drawPlot()');assert.equal(g.run('severity(state.card)'),'failure');assert.ok(g.operations.strokes>0);});
