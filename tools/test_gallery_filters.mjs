import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {missionKind,matchesGallery,featuredOrder} from '../docs/gallery_filters.js';
test('provenance uses explicit identification or documented calendar match, not an arbitrary name',()=>{
 assert.equal(missionKind({mission_label:'Cassini-looking original'}),'original');
 assert.equal(missionKind({historical_match:{name:'Cassini'}}),'reconstruction');
 assert.equal(missionKind({mission_kind:'reconstruction'}),'reconstruction');
 assert.ok(matchesGallery({sequence:'EVEEJ'},'original','EVEEJ'));
 assert.ok(!matchesGallery({sequence:'EVVEJ'},'original','EVEEJ'));
 assert.ok(!matchesGallery({sequence:'EVEEJ',mission_kind:'reconstruction'},'original'));
 assert.ok(matchesGallery({mission_kind:'reconstruction'},'both'));
});
test('complex original is featured before Mercury and reconstructions, even with missing spotlight fields',()=>{
 const annotations=JSON.parse(fs.readFileSync(new URL('../docs/data/mission_annotations.json',import.meta.url))).missions;
 const sample=[{id:'mercury',sequence:'EVVMe',received:9e15},{id:'juno',...annotations['8ea27f8c3842a8a9b17a91aed85cfd74c6c55c6052e8a480c0a07a45330f0aca']},{id:'4d76acaf1f6f',...annotations['4d76acaf1f6f']}];
 assert.equal(sample.sort(featuredOrder)[0].id,'4d76acaf1f6f');
 const actual=JSON.parse(fs.readFileSync(new URL('../docs/data/index.json',import.meta.url))).cases.map(c=>({...c,...annotations[c.id]}));
 assert.equal(actual.sort(featuredOrder)[0].id,'4d76acaf1f6f');
 assert.equal(featuredOrder({id:'b'},{id:'a'}),1);
 assert.equal(annotations['claudius-uop-2045'].mission_kind,'original');
 assert.equal(annotations['tianwen4-concept'].mission_kind,'reconstruction');
 assert.equal(annotations['4fed974cbffb'].mission_kind,'reconstruction');
});
