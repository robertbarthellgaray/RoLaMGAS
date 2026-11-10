import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createHash} from 'node:crypto';

test('queued package retains the selected dwarf patch and catalog while integration runs',async()=>{
 const gui=fs.readFileSync(new URL('../gui.js',import.meta.url),'utf8');
 const source=gui.slice(gui.indexOf('async function exportPackage('),gui.indexOf('async function refreshCache('));
 const elements={packageModel:{value:'RTG'},patchDwarfPlanet:{checked:true},dwarfCatalogPath:{value:'/opt/Celestia/data/dwarfplanets.ssc'},packageButton:{},packageStatus:{},integrate:{},postFlybyMonths:{value:'6'},exportPowered:{checked:false}};
 let payload;
 const ctx=vm.createContext({state:{selected:'0123456789ab',run:'saved'},$:(id)=>elements[id],arrivalAltitude:()=>null,arrivalInclination:()=>null,checkExport(){},api:async(path,data)=>{payload=data;return {state:'integrating'}}});
 vm.runInContext(source,ctx);await vm.runInContext('exportPackage()',ctx);
 assert.equal(payload.patch_dwarf_planet,true);assert.equal(payload.dwarf_catalog_path,'/opt/Celestia/data/dwarfplanets.ssc');
 elements.patchDwarfPlanet.checked=false;elements.dwarfCatalogPath.value='';
 assert.equal(ctx.state.pendingPackage.patch.enabled,true);assert.equal(ctx.state.pendingPackage.patch.catalog,'/opt/Celestia/data/dwarfplanets.ssc');
 assert.match(gui,/exportPackage\(pending.model,pending.patch\)/);
});

test('six named mission pages link to audited finite-radius downloads and explicit export budgets',()=>{
 const ids=['f53fc65c9329','0fc1f2bcd586','dd67c26fd41f','9ca55df1c55c','35bd4d9c6e03','552363ae7812'];
 const root=new URL('../docs/',import.meta.url),read=p=>JSON.parse(fs.readFileSync(new URL(p,root),'utf8'));
 for(const id of ids){
  const c=read('data/cases/'+id+'.json'),f=c.trajectory_files,r=read(f.integration_report);
  assert.equal(f.finite_radius,true);assert.equal(r.numerical_validation_passed,true);assert.equal(r.no_sample_bracketed_planet_or_sun_impacts,true);
  assert.equal(f.rows,r.rows);assert.equal(f.passes_original_onboard_budget,r.passes_original_onboard_budget);
  assert.equal(createHash('sha256').update(fs.readFileSync(new URL(f.xyzv,root))).digest('hex'),f.xyzv_sha256);
  assert.equal(createHash('sha256').update(fs.readFileSync(new URL(f.csv,root))).digest('hex'),f.csv_sha256);
  assert.ok(fs.existsSync(new URL(f.burns,root)));assert.match(f.note,/onboard delta-v/);
  if(!r.passes_original_onboard_budget)assert.match(f.note,/Exceeds the original/);
 }
});
