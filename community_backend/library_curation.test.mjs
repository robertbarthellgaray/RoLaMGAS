import test from 'node:test';
import assert from 'node:assert/strict';
import {clearlyDominates,trimAlternatives,groupLaunches,launchTimestamp} from '../docs/library_curation.js';
const base={id:'a',target:'Saturn',sequence:'EJS',bodies:['Earth','Jupiter','Saturn'],model:'Shared pass',classification:'pass',start:2466519.5,c3:20,years:8,vinf:6,burns_mps:100};
const worse={...base,id:'b',c3:35,years:12};

test('small bodies trim modest material losses despite tiny arrival-speed and burn changes',()=>{
 const a={...base,target:'Pluto',target_id:'999',bodies:['Earth','Jupiter','Pluto'],sequence:'EJX',c3:40,years:20,vinf:10.1,burns_mps:110};
 const b={...a,id:'b',c3:45,years:21,vinf:10,burns_mps:100,start:a.start+4*365.25};
 assert.equal(clearlyDominates(a,b),true);
 assert.equal(clearlyDominates({...a,vinf:11},b),true);
 assert.equal(clearlyDominates({...a,vinf:13},b),false);
 assert.equal(clearlyDominates({...a,burns_mps:126},b),false);
 assert.equal(clearlyDominates({...a,years:22},b),false);
 const trimmed=trimAlternatives([b,a]);assert.equal(trimmed.hidden.get('b'),'a');
 assert.equal(trimAlternatives([b,a],new Set(['b'])).hidden.size,0);
});

test('a long small-body trip must buy substantial arrival speed reduction per extra year',()=>{
 const fast={...base,target:'Makemake',target_id:'20136472',sequence:'ESX',bodies:['Earth','Saturn','Makemake'],years:20,c3:120,vinf:12};
 const slow={...fast,id:'slow',years:35,c3:125,vinf:6};
 assert.equal(clearlyDominates(fast,slow),true); // 6 km/s does not justify 15 extra years.
 assert.equal(clearlyDominates(fast,{...slow,vinf:4.5}),false); // 7.5 km/s preserves the tradeoff.
 assert.equal(clearlyDominates(fast,{...slow,years:22.5,vinf:9.7}),true); // Less than 20% improvement.
 assert.equal(clearlyDominates(fast,{...slow,years:22.5,vinf:9.6}),false);
 assert.equal(clearlyDominates(fast,{...slow,c3:100}),false); // A lower-energy route stays available.
});
test('trim only material same-sequence losses without hiding speed or burn tradeoffs',()=>{
 assert.equal(clearlyDominates(base,worse),true);
 for(const change of [{vinf:5},{burns_mps:0},{c3:15},{years:7},{sequence:'EVEES'},{target:'Neptune'},{bodies:['Earth','Saturn']},{start:base.start+4*365.25},{classification:'yellow'}]){
  const a=change.classification?{...base,...change}:base,b=change.classification?worse:{...worse,...change};assert.equal(clearlyDominates(a,b),false,JSON.stringify(change));
 }
 assert.equal(clearlyDominates(base,{...worse,c3:21,years:8.1}),false);
 assert.equal(clearlyDominates({...base,classification:'pass'},{...worse,classification:'yellow'}),true);
});
test('keep named and integrated missions; stable retained witnesses and no input mutation',()=>{
 const rows=[worse,{...worse,id:'named'},{...worse,id:'integrated',spotlight:true},{...worse,id:'research',model:'Research patched-conic recreation'},base],copy=JSON.stringify(rows);
 const result=trimAlternatives(rows,new Set(['named']));
 assert.deepEqual([...result.hidden],[['b','a']]);assert.equal(JSON.stringify(rows),copy);
 assert.deepEqual(trimAlternatives([...rows].reverse(),new Set(['named'])).hidden,result.hidden);
});
test('launch window is checked against the retained witness, not a distant chain',()=>{
 const rows=[{...base,id:'early',start:base.start-5*365.25,c3:10,years:6},{...base,id:'middle',start:base.start-2.5*365.25},worse];
 const r=trimAlternatives(rows);assert.equal(r.hidden.get('middle'),'early');assert.ok(!r.hidden.has('b'));
 for(const [id,witness] of r.hidden){assert.ok(!r.hidden.has(witness));assert.ok(clearlyDominates(rows.find(c=>c.id===witness),rows.find(c=>c.id===id)));}
});
test('filtering launch years first restores an otherwise trimmed launch opportunity',()=>{
 const rows=[base,{...worse,start:base.start+365.25}];assert.equal(trimAlternatives(rows).hidden.size,1);assert.equal(trimAlternatives(rows.slice(1)).rows.length,1);
});
test('a cheaper candidate with worse measured flyby continuity cannot hide a better-connected option',()=>{
 assert.equal(clearlyDominates({...base,mismatch_max_mps:500},{...worse,mismatch_max_mps:400}),false);
 assert.equal(clearlyDominates({...base,mismatch_max_mps:0},{...worse,mismatch_max_mps:400}),true);
 assert.equal(clearlyDominates(base,{...worse,mismatch_max_mps:400}),false);
});
test('near-equal launch costs cannot produce a comparison pointing to another trimmed record',()=>{
 const rows=[{...base,id:'older',start:base.start-5*365.25,c3:20.00000004,years:6},{...base,id:'middle',start:base.start-2.5*365.25,c3:20.00000005},worse];
 const result=trimAlternatives(rows);for(const [id,witness] of result.hidden){assert.ok(!result.hidden.has(witness));assert.ok(clearlyDominates(rows.find(c=>c.id===witness),rows.find(c=>c.id===id)));}
});
test('monthly groups keep exact TDB epochs and distinguish sequence, destination and month',()=>{
 const jan={...base,start:2466529.5+13/24+25/1440+42/86400}; // 2041-01-10
 const rows=[jan,{...jan,id:'same-month',start:jan.start+1},{...jan,id:'feb',start:jan.start+31},{...jan,id:'different-sequence',sequence:'EVEEJS'},{...jan,id:'different-target',target:'Neptune'}],groups=groupLaunches(rows);
 assert.equal(groups.length,4);assert.equal(groups[0].month,'2041-01');assert.equal(groups[0].rows.length,2);assert.equal(groups[1].month,'2041-02');assert.match(launchTimestamp(jan),/13:25:42 TDB$/);
 assert.equal(groups.flatMap(g=>g.rows).length,rows.length);
});
