import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const gui=fs.readFileSync(new URL('../gui.js',import.meta.url),'utf8');
const flow=gui.slice(gui.indexOf('function showMoonSearchIntent('),gui.indexOf('function changeMode('));
const setup=gui.slice(gui.indexOf('function setupMoonTarget('),gui.indexOf('async function startMoonTarget('));
function context(){
 const nodes={},node=id=>nodes[id]??={value:'',children:[],append(x){this.children.push(x)},replaceChildren(){this.children=[]},selectedOptions:[],querySelector(){return {}}};
 const radio={checked:false},routes=[];
 const state={moonIntent:null,boot:{moon_targets:{Jupiter:[{id:'502',name:'Europa'},{id:'503',name:'Ganymede'}],Saturn:[{id:'606',name:'Titan'}]},routes:[{id:'EJ',target:'Jupiter'},{id:'EVEEJ',target:'Jupiter'},{id:'ES',target:'Saturn'}]},limits:{}};
 const ctx=vm.createContext({state,$:node,targetMode:()=>radio.checked?'planet':'object',document:{querySelector:()=>radio},setRoutes:r=>routes.push(r),message(){},clearTimeout(){},moonTargetControls(){},checkMoonTarget(){},element:(tag,text)=>({tag,text})});
 vm.runInContext(flow+setup,ctx);return {ctx,state,node,radio,routes};
}
test('Europa selects Jupiter repository routes while retaining the requested moon',()=>{
 const {ctx,state,node,radio,routes}=context();
 state.targetNeedsResolution=true;
 assert.equal(vm.runInContext("selectMoonDestination({id:'502',name:'Europa',parent_body:'Jupiter'})",ctx),true);
 assert.equal(node('planet').value,'Jupiter');assert.equal(radio.checked,true);assert.equal(node('objectBox').hidden,true);
 assert.equal(state.targetNeedsResolution,false);
 assert.deepEqual(JSON.parse(JSON.stringify(state.moonIntent)),{parent:'Jupiter',moon_id:'502',moon_name:'Europa'});
 assert.deepEqual(Array.from(routes[0]),['EJ','EVEEJ']);assert.match(node('moonSearchText').textContent,/Europa/);assert.equal(node('moonSearchNotice').hidden,false);
 node('planet').value='Saturn';vm.runInContext('showMoonSearchIntent()',ctx);assert.equal(node('moonSearchNotice').hidden,true);
});
test('candidate moon panel restores Europa from the saved search and stays visible for Jupiter',()=>{
 const {ctx,state,node}=context();state.limits.moon_target={parent:'Jupiter',moon_id:'502'};
 vm.runInContext("setupMoonTarget({bodies:['Earth','Jupiter']})",ctx);
 assert.equal(node('moonTargetMenu').hidden,false);assert.equal(node('moonTargetMenu').open,true);assert.equal(node('moonTargetBody').value,'502');
 assert.equal(node('moonTargetMode').value,'approach');
});
test('unknown moons do not silently switch to a different satellite',()=>{
 const {ctx,state}=context();assert.equal(vm.runInContext("selectMoonDestination({id:'59999',name:'Unknown',parent_body:'Jupiter'})",ctx),false);assert.equal(state.moonIntent,null);
});
