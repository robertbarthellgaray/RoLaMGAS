import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const source=fs.readFileSync(new URL('../gui.js',import.meta.url),'utf8').split("$('reuse').onclick=")[0];
function form(mode='planet'){
 const elements={};for(const id of ['planet','customSequences','eventWindows','minC3','maxC3','c3SeedBoundary','missionProfile','launchStart','launchEnd','tolerance','maxDsm','maxSingleDsm','maxPoweredFlyby','maxArrival','maxYears','workers','batches','seed','samples','starts','branches','nfev','keep','cadence','objective','costStarts','customMin','customMax','arrivalDate','arrivalTolerance','transferDirection','poweredFlybys','formMessage'])elements[id]={value:'1',checked:false};
 Object.assign(elements,{planet:{value:'Jupiter'},minC3:{value:'6.25'},maxC3:{value:'100'},customSequences:{value:''},eventWindows:{value:''},customMin:{value:'30'},customMax:{value:'18262.5'},routes:{querySelectorAll:()=>[{value:'EJ'}]},altitudes:{querySelectorAll:()=>[]}});
 const selector={value:mode},ctx=vm.createContext({document:{getElementById:id=>elements[id],querySelector:()=>selector},structuredClone});vm.runInContext(source,ctx);
 vm.runInContext("state.target={name:'Pluto Barycenter',id:'9',command:'9'};state.preset={custom_leg_days:[30,18262.5]}",ctx);
 return {elements,selector,run:s=>vm.runInContext(s,ctx)};
}
test('hidden object leg limits cannot block or contaminate a planet search',()=>{
 const f=form();f.run('syncTargetLegFields()');
 assert.equal(f.elements.customMax.disabled,true);assert.equal(f.elements.customMin.disabled,true);
 f.elements.customMax.value='';assert.equal(f.run('gather().custom_leg_days'),undefined);
});
test('Horizons searches accept the fractional 50-year default and keep active limits',()=>{
 const f=form('object');f.run('syncTargetLegFields()');assert.equal(f.elements.customMax.disabled,false);
 assert.equal(f.run('gather().custom_leg_days[1]'),18262.5);
 const html=fs.readFileSync(new URL('../gui.html',import.meta.url),'utf8');
 for(const id of ['customMin','customMax'])assert.match(html.match(new RegExp('<input[^>]*id="'+id+'"[^>]*>'))[0],/step="any"/);
});
test('invalid fields expand their controls and produce a visible Start Search explanation',()=>{
 const f=form();const details={tagName:'DETAILS',open:false,parentElement:null};
 f.elements.invalid={target:{id:'samples',labels:[{textContent:'Samples / sequence'}],validationMessage:'Value must be at least 8',parentElement:details}};
 f.run('reportInvalidSearchInput(document.getElementById("invalid"))');
 assert.equal(details.open,true);assert.match(f.elements.formMessage.textContent,/Cannot start search: Samples/);
 assert.match(f.elements.formMessage.textContent,/at least 8/);
});
