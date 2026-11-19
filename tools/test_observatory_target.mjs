import test from 'node:test';
import assert from 'node:assert/strict';
import {targetContext} from '../docs/observatory_target.js';

test('major planets use the existing planet meshes',()=>{
 assert.equal(targetContext({target:'Saturn'},2451545,()=>[1,2,3]),null);
});
test('small-body encounter is shown without pretending it is a dated position',()=>{
 for(const name of ['Pluto','Halley','1036 Ganymed']){
  const orbit=[[2,3,4],[3,4,5]],mission={target:name,events:[{body:'Earth',position_au:[1,0,0]},{body:name,position_au:[20,3,4]}],planet_paths:[{body:name,points:orbit}]};
  const target=targetContext(mission,2451545,()=>null);
  assert.deepEqual(target.point,[20,3,4]);assert.equal(target.label,name+' · at encounter');assert.equal(target.dated,false);assert.equal(target.orbit,orbit);
 }
});
test('dated target vectors take precedence and invalid positions are omitted',()=>{
 const mission={target:'Eris',events:[{body:'Eris',position_au:[80,0,0]}]};
 const target=targetContext(mission,100,(name,jd)=>{assert.equal(name,'Eris');assert.equal(jd,100);return [79,1,0]});
 assert.deepEqual(target.point,[79,1,0]);assert.equal(target.label,'Eris');assert.equal(target.dated,true);
 assert.equal(targetContext({target:'Unknown',events:[]},100,()=>null),null);
 assert.equal(targetContext({target:'Bad',events:[{position_au:[NaN,0,0]}]},100),null);
});
