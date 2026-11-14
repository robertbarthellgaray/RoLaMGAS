import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
const gui=fs.readFileSync(new URL('../gui.js',import.meta.url),'utf8');
const source=gui.slice(gui.indexOf('function moonTargetControls('),gui.indexOf("$('reuse').onclick="));
function context(api){
 const nodes={};const node=id=>nodes[id]??=( {value:'',children:[],append(...x){this.children.push(...x)},replaceChildren(...x){this.children=[...x]},querySelector(){return this.entry??={}},selectedOptions:[{textContent:'Titan'}]});
 for(const [id,value]of Object.entries({moonTargetMode:'approach',moonTargetBody:'606',moonTargetAltitude:'1000',moonTargetCap:'700',moonTargetEffort:'quick'}))node(id).value=value;
 const ctx=vm.createContext({state:{run:'test',selected:'0123456789ab'},$:node,element:(tag,text)=>({tag,text,children:[],append(...x){this.children.push(...x)}}),fmt:(x,n)=>Number(x).toFixed(n),api,setTimeout:()=>1,clearTimeout(){},Date});vm.runInContext(source,ctx);return {ctx,nodes,node};
}
test('moon targeting sends the selected altitude/mode and retains its separate branch',async()=>{
 const requests=[];const {ctx,node}=context(async(path,data)=>{requests.push([path,data]);return path.includes('status')?{state:'none'}:{branch:'abcdef012345'}});
 node('moonTargetMode').value='impact';node('moonTargetAltitude').value='999';
 node('moonTargetInclination').value='90';
 await vm.runInContext('startMoonTarget()',ctx);
 assert.equal(requests[0][0],'/api/target-moon');assert.equal(requests[0][1].altitude_km,0);assert.equal(requests[0][1].moon_id,'606');
 assert.equal(requests[0][1].inclination_deg,90);
 assert.equal(ctx.state.moonJob.branch,'abcdef012345');assert.equal(node('stopMoonTarget').hidden,false);
});
test('late status from a different selected candidate cannot replace the inspector',async()=>{
 let resolve;const {ctx,node}=context(()=>new Promise(r=>resolve=r));
 const pending=vm.runInContext('checkMoonTarget()',ctx);ctx.state.selected='bbbbbbbbbbbb';resolve({state:'finished',message:'old result',branch:'abcdef012345'});await pending;
 assert.equal(node('moonTargetStatus').textContent,undefined);assert.equal(ctx.state.moonJob,undefined);
});
test('completed branch offers full states, burn accounting and endpoint downloads',async()=>{
 const report={moon_body:'Titan',target_mode:'entry',target_altitude_km:1270,target_date:'2035-11-27 TDB',moon_relative_speed_kms:8.49,added_correction_delta_v_kms:.0146,total_onboard_delta_v_kms:.4285,passes_added_burn_limit:true,minimum_found_note:'Lowest tested timing'};
 const {ctx,node}=context(async()=>({state:'finished',message:'Saved',elapsed_seconds:12,branch:'abcdef012345',report}));
 await vm.runInContext('checkMoonTarget()',ctx);
 const result=node('moonTargetResult');const links=result.children.find(x=>x.tag==='div').children;
 assert.ok(links.find(a=>a.href.endsWith('/trajectory.xyzv')));assert.ok(links.find(a=>a.href.endsWith('/arrival_state.json')));assert.ok(links.find(a=>a.href.endsWith('/burns.csv')));
 assert.match(result.children[0].text,/8.490 km\/s/);assert.match(result.children[1].text,/428.50 m\/s/);assert.equal(node('targetMoon').disabled,false);
});
test('Titan-only entry is disabled for airless moons',()=>{
 const {ctx,node}=context(async()=>({state:'none'}));node('moonTargetMode').value='entry';node('moonTargetBody').selectedOptions=[{textContent:'Enceladus'}];
 vm.runInContext('moonTargetControls()',ctx);assert.equal(node('moonTargetMode').value,'approach');assert.equal(node('moonTargetMode').entry.disabled,true);
});
test('fixed entry point sends east longitude and omits the separate inclination constraint',async()=>{
 const requests=[];const {ctx,node}=context(async(path,data)=>{requests.push([path,data]);return path.includes('status')?{state:'none'}:{branch:'abcdef012345'}});
 node('moonTargetMode').value='entry';node('moonTargetAltitude').value='1270';node('moonTargetLocation').checked=true;node('moonTargetLatitude').value='4';node('moonTargetLongitude').value='162.5';node('moonTargetInclination').value='90';
 await vm.runInContext('startMoonTarget()',ctx);assert.equal(requests[0][1].target_latitude_deg,4);assert.equal(requests[0][1].target_longitude_deg,162.5);assert.equal(requests[0][1].inclination_deg,null);
});
test('published Titan branch has a full finite trajectory and an honest 2035 label',()=>{
 const root=new URL('../docs/',import.meta.url),read=p=>JSON.parse(fs.readFileSync(new URL(p,root),'utf8'));
 const c=read('data/cases/dragonfly-titan-entry-2035.json'),f=c.trajectory_files,r=read(f.integration_report);
 assert.equal(f.finite_radius,true);assert.equal(c.arrival_date,'2035-11-27');assert.match(c.note,/late 2034/);assert.match(c.note,/not.*operational trajectory/);
 assert.equal(c.moon_arrival.atmosphere_modeled,false);assert.equal(c.moon_arrival.landing_site_targeted,false);
 assert.ok(r.independent_endpoint_error_km<.1);assert.equal(r.soi_delta_v_kms,0);assert.equal(c.desktop_handoff_source,'6ef2b7edc240');
 assert.equal(createHash('sha256').update(fs.readFileSync(new URL(f.xyzv,root))).digest('hex'),f.xyzv_sha256);
 const rows=fs.readFileSync(new URL(f.xyzv,root),'utf8').trim().split('\n').map(line=>line.trim().split(/\s+/).map(Number));
 assert.equal(rows.length,f.rows);assert.equal(rows[0][0],c.start);assert.equal(rows.at(-1)[0],c.end);assert.ok(rows.every((row,i)=>row.length===7&&row.every(Number.isFinite)&&(!i||row[0]>rows[i-1][0])));
 assert.ok(Math.abs(c.burns.reduce((sum,b)=>sum+b.magnitude_mps,0)-c.burns_mps)<1e-6);
 assert.ok(c.burns_mps<500);assert.ok(r.source_join_position_error_km<.01);
});
