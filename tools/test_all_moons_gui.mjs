import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const source=fs.readFileSync(new URL('../gui.js',import.meta.url),'utf8');
const flow=source.slice(source.indexOf('function showMoonSearchIntent('),source.indexOf('function changeMode('));
const setup=source.slice(source.indexOf('function setupMoonTarget('),source.indexOf('async function startMoonTarget('));
const catalog=JSON.parse(fs.readFileSync(new URL('../celestia_assets/satellite_catalog.json',import.meta.url),'utf8'));
function context(){
 const nodes={},node=id=>nodes[id]??={value:'',children:[],selectedOptions:[],append(x){this.children.push(x)},replaceChildren(){this.children=[]},querySelector(){return {}}};
 const eris=catalog.systems.find(s=>s.name==='Eris'),makemake=catalog.systems.find(s=>s.name==='Makemake');
 const state={boot:{moon_aliases:{'136199 eris (2003 ub313)':'Eris','eris (primary body)':'Eris'},moon_targets:{Eris:eris.moons,Makemake:makemake.moons},moon_parents:{Eris:{name:eris.fullname,id:'20136199',command:'136199;',kind:'small_body'}},routes:[]},limits:{}};
 const ctx=vm.createContext({state,$:node,document:{querySelector:()=>({})},targetMode:()=> 'object',setRoutes(){},message(){},clearTimeout(){},moonTargetControls(){},checkMoonTarget(){},structuredClone,element:(tag,text)=>({tag,text})});
 vm.runInContext(flow+setup,ctx);return {ctx,state,node};
}
test('an imported Eris SB name shows Dysnomia in the moon menu',()=>{
 const {ctx,state,node}=context();vm.runInContext("setupMoonTarget({bodies:['Earth','136199 Eris (2003 UB313)']})",ctx);
 assert.equal(state.moonParent,'Eris');assert.equal(node('moonTargetMenu').hidden,false);
 assert.equal(node('moonTargetBody').children[0].value,'120136199');assert.equal(node('moonTargetBody').children[0].disabled,false);
 assert.equal(node('moonAllowProjection').checked,false);
});
test('Dysnomia selects an Eris search rather than an invalid planet dropdown',()=>{
 const {ctx,state,node}=context();assert.equal(vm.runInContext("selectMoonDestination({id:'120136199',name:'Dysnomia',parent_body:'Eris'})",ctx),true);
 assert.equal(state.target.id,'20136199');assert.equal(state.moonIntent.parent,'Eris');assert.equal(node('objectBox').hidden,false);
 assert.equal(node('moonSearchNotice').hidden,false);
});
test('missing moon data keeps the parent menu visible and does not enable a fabricated orbit',()=>{
 const {ctx,node}=context();vm.runInContext("setupMoonTarget({bodies:['Earth','Makemake']})",ctx);
 assert.equal(node('moonTargetMenu').hidden,false);assert.ok(node('moonTargetBody').children.length);
 assert.equal(node('moonTargetBody').children[0].disabled,true);assert.equal(node('targetMoon').disabled,true);
 assert.match(node('moonTargetStatus').textContent,/missing physical or orbital data/);
});
test('unknown-radius moons use center-distance controls and cannot request surface impact',()=>{
 const html=fs.readFileSync(new URL('../gui.html',import.meta.url),'utf8');assert.match(html,/id="moonDistanceLabel"/);
 assert.match(source,/Closest approach distance from moon center/);assert.match(source,/impact\.disabled=!!selected\?\.radius_unknown/);
});
