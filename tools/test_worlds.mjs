import test from 'node:test';
import assert from 'node:assert/strict';
import {bodyCategory,registerBodyPhysical,NEPTUNE_SMA_AU} from '../docs/library_analysis.js';
import {smallBodyCards,smallBodyBriefing} from '../docs/world_guide.js';

test('Neptune SMA cutoff groups minor bodies without moving comets or planets',()=>{
 registerBodyPhysical({bodies:{'20999101':{sma_au:NEPTUNE_SMA_AU+.001},'20999102':{sma_au:NEPTUNE_SMA_AU},'1000999':{sma_au:400}}});
 assert.equal(bodyCategory('Test outer body','20999101'),'Dwarf planets & TNOs');
 assert.equal(bodyCategory('Test inner body','20999102'),'Asteroids');
 assert.equal(bodyCategory('C/2099 Test','1000999'),'Comets');
 assert.equal(bodyCategory('Neptune','899'),'Planets');
 assert.equal(bodyCategory('Ceres','20000001'),'Dwarf planets & TNOs');
});
test('body sorting distinguishes diameter, SMA and counts; unknown values stay last',()=>{
 const rows=[{target:'Large',target_id:'a'},{target:'Near',target_id:'b'},{target:'Near',target_id:'b'},{target:'Unknown',target_id:'c'}];
 const physical={bodies:{a:{diameter_km:1000,sma_au:90},b:{diameter_km:200,sma_au:31}}};
 const order=sort=>[...smallBodyCards(rows,'All','Dwarf planets & TNOs',physical,sort).matchAll(/data-small-body="([^"]+)"/g)].map(m=>m[1]);
 assert.deepEqual(order('diameter'),['All','Large','Near','Unknown']);
 assert.deepEqual(order('sma'),['All','Near','Large','Unknown']);
 assert.deepEqual(order('count'),['All','Near','Large','Unknown']);
});
test('Pluto aliases show its image and SMA; untrusted labels stay escaped',()=>{
 const physical={bodies:{999:{sma_au:39.482,diameter_km:2376.6}}};
 const out=smallBodyBriefing('Pluto','Dwarf planets & TNOs',physical,[{target:'Pluto',target_id:'9'}]);
 assert.match(out,/pluto.jpg/);assert.match(out,/39\.482/);
 const haumea=smallBodyBriefing('Haumea','Dwarf planets & TNOs',{bodies:{h:{sma_au:43.1,diameter_km:1430}}},[{target:'Haumea',target_id:'h'}]);
 assert.match(haumea,/haumea.jpg/);assert.match(haumea,/Artist’s impression/);assert.match(haumea,/Mean reference diameter/);
 assert.match(smallBodyCards([{target:'Haumea',target_id:'h'}],'All','Dwarf planets & TNOs',{bodies:{h:{diameter_km:1430}}}),/haumea-disc/);
 const html=smallBodyCards([{target:'<img onerror=bad>',target_id:'x'}],'All','Asteroids',{},'diameter');
 assert.doesNotMatch(html,/<img onerror/);assert.match(html,/&lt;img onerror=bad&gt;/);
});
