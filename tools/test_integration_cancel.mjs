import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import fs from 'node:fs';
const js=fs.readFileSync(new URL('../gui.js',import.meta.url),'utf8'),helpers=js.slice(js.indexOf('function integrationControls('),js.indexOf('async function integrate(){'));
test('cancel control addresses the actual active job and resets after a terminal state',async()=>{
 const elements=Object.fromEntries(['exportSharingStatus','cancelIntegration','integrate','exportStatus'].map(k=>[k,{}]));const state={run:'current',selected:'b'.repeat(12),pendingPackage:{}};let sent,checked=false;
 const context=vm.createContext({state,$:id=>elements[id],setTimeout:()=>1,checkExport:async()=>{checked=true},api:async(path,value)=>{sent={path,value};return {state:'cancelled'}}});vm.runInContext(helpers,context);
 vm.runInContext("integrationControls({state:'none',active_integration:{run:'other',candidate:'aaaaaaaaaaaa'}})",context);assert.equal(elements.cancelIntegration.hidden,false);assert.equal(elements.integrate.disabled,true);
 await vm.runInContext('cancelIntegration()',context);assert.equal(sent.path,'/api/integration/cancel');assert.equal(sent.value.run,'other');assert.equal(sent.value.candidate,'a'.repeat(12));assert.equal(state.pendingPackage,null);assert.ok(checked);
 vm.runInContext("integrationControls({state:'cancelled',active_integration:null})",context);assert.equal(elements.cancelIntegration.hidden,true);assert.equal(elements.integrate.disabled,false);
});
