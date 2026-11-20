import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const source=fs.readFileSync(new URL('../gui.js',import.meta.url),'utf8');
test('one target patch control replaces the separate dwarf checkbox and preserves step/duration controls',()=>{
 const html=fs.readFileSync(new URL('../gui.html',import.meta.url),'utf8');
 assert.doesNotMatch(html,/id="patchDwarfPlanet"/);assert.match(html,/Patch target with JPL data/);
 for(const id of ['jplPatchDays','jplPatchUnits','jplPatchStep','patchTargetMoon'])assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/default: 1 year total/);assert.match(html,/hard floor is 5/);
});
test('Pluto moon destinations keep the object identity and expose all five moons in saved candidates',()=>{
 const nodes={},node=id=>nodes[id]??={value:'',children:[],append(x){this.children.push(x)},replaceChildren(){this.children=[]},querySelector(){return {}}};
 const radio={checked:false};const moons=['Charon','Nix','Hydra','Kerberos','Styx'].map((name,i)=>({id:String(901+i),name}));
 const state={boot:{moon_targets:{Pluto:moons},moon_parents:{Pluto:{name:'Pluto',id:'999',command:'999'}},routes:[]},limits:{moon_target:{parent:'Pluto',moon_id:'902'}}};
 const ctx=vm.createContext({state,$:node,targetMode:()=>state.target?'object':'planet',document:{querySelector:()=>radio},setRoutes(){},message(){},clearTimeout(){},moonTargetControls(){},checkMoonTarget(){},structuredClone,element:(tag,text)=>({tag,text})});
 vm.runInContext(source.slice(source.indexOf('function showMoonSearchIntent('),source.indexOf('function changeMode('))+source.slice(source.indexOf('function setupMoonTarget('),source.indexOf('async function startMoonTarget(')),ctx);
 assert.equal(vm.runInContext("selectMoonDestination({id:'901',name:'Charon',parent_body:'Pluto'})",ctx),true);
 assert.equal(state.target.id,'999');assert.equal(node('objectBox').hidden,false);assert.equal(node('moonSearchNotice').hidden,false);
 vm.runInContext("setupMoonTarget({bodies:['Earth','134340 Pluto (1930 BM)']})",ctx);
 assert.equal(node('moonTargetMenu').hidden,false);assert.equal(node('moonTargetBody').children.length,5);assert.equal(node('moonTargetBody').value,'902');
});
