import test from 'node:test';import assert from 'node:assert/strict';import {combinedMismatch} from '../docs/mismatch_screen.js';
test('combined threshold is strict and separate from each flyby peak',()=>{
 assert.equal(combinedMismatch({flybys:[{mismatch_mps:600},{mismatch_mps:450}]}).red,true);
 assert.equal(combinedMismatch({flybys:[{mismatch_mps:600},{mismatch_mps:400}]}).red,false);
 assert.equal(combinedMismatch({}, {metrics:{max_vinf_mismatch_mps:1001}}).red,true);
 assert.equal(combinedMismatch({}, {metrics:{max_vinf_mismatch_mps:600}}).sum_mps,null);
 assert.equal(combinedMismatch({}, {metrics:{combined_vinf_mismatch_mps:1050,max_vinf_mismatch_mps:600}}).red,true);
});
