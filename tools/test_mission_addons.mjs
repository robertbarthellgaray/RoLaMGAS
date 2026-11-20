import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import {createHash} from 'node:crypto';
import {MISSION_ADDONS,missionAddons,appendMissionAddons} from '../docs/mission_addons.js';
const read=name=>fs.readFileSync(new URL('../docs/'+name,import.meta.url),'utf8');
test('curated addon associations match the manifest and use exact mission IDs',()=>{
 const assets=JSON.parse(read('data/celestia_addons.json')).assets;
 assert.deepEqual(MISSION_ADDONS,assets.filter(a=>a.mission_ids?.length).map(({title,source_url,mission_ids})=>({title,source_url,mission_ids})));
 for(const addon of MISSION_ADDONS){assert.match(addon.source_url,/^https:\/\/celestia.mobi\/resources\/item\/[A-F0-9-]+$/);for(const id of addon.mission_ids)assert.equal(missionAddons({id})[0].title,addon.title);}
 assert.deepEqual(missionAddons({id:'unrelated',title:'Eris Explorer'}),[]);
 assert.equal(missionAddons({community_record:{id:MISSION_ADDONS[0].mission_ids[0]}})[0].title,'Eris Explorer');
});
test('mission links are visible external addon pages rather than downloads',()=>{
 const original=globalThis.document,nodes=[];globalThis.document={createElement:tag=>({tag})};
 try{appendMissionAddons({append:a=>nodes.push(a)},{id:'c16155480c4d'});assert.equal(nodes.length,1);assert.match(nodes[0].textContent,/INFINITY/);assert.equal(nodes[0].target,'_blank');assert.equal(nodes[0].rel,'noopener noreferrer');assert.equal(nodes[0].download,undefined);}finally{globalThis.document=original}
 assert.ok(read('app.js').includes('appendMissionAddons(extras,c,canonicalId)'));
});
test('INFINITY showcase retains artwork attribution, image integrity and two-way links',()=>{
 const data=JSON.parse(read('data/celestia_addons.json')),addon=data.assets.find(a=>a.slug==='infinity'),html=read('celestia.html');
 assert.equal(data.spacecraft_count,5);assert.equal(addon.id,'BB56D66D-38AC-4712-ACB5-492916136ED3');assert.equal(addon.trajectory_credit,'ReachStar on Bilibili');
 assert.equal(createHash('sha256').update(fs.readFileSync(new URL('../docs/'+addon.image,import.meta.url))).digest('hex'),addon.image_sha256);
 assert.ok(html.includes(addon.source_url));assert.ok(html.includes('Original trajectory: ReachStar on Bilibili'));
 for(const a of data.assets.filter(a=>a.mission_ids?.length))assert.ok(html.includes('./#mission='+a.mission_ids[0]));
});

test('an exact curated association survives a repository same-day duplicate alias',()=>{
 assert.equal(missionAddons({id:'deduplicated-case'},id=>id==='c16155480c4d'?'deduplicated-case':id)[0].title,'INFINITY');
});
