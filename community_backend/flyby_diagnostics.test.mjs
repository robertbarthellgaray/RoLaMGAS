import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {estimateFlybys,planetState,poweredGeometry,storedMismatch} from '../docs/flyby_diagnostics.js';
import {summaryFor} from '../docs/community.js';
const read=path=>JSON.parse(fs.readFileSync(new URL('../'+path,import.meta.url),'utf8'));
const record=read('studies/flyby_audits/4f2144477cd4/shared_record.json'),audit=read('studies/flyby_audits/4f2144477cd4/audit.json'),context=read('studies/flyby_audits/4f2144477cd4/exact_jpl_fixture.json');
test('the old public upload already records the maximum mismatch independently of zero modeled burns',()=>{
 assert.equal(storedMismatch(record),450.51030810996906);assert.equal(record.metrics.total_dsm_kms,0);
 const summary=summaryFor(record);assert.equal(summary.burns_mps,0);assert.equal(summary.mismatch_max_mps,450.51030810996906);
 assert.equal(storedMismatch({metrics:{}}),null);
});
test('browser analytic flyby geometry agrees with the desktop Python calculation and preserves the source',()=>{
 const before=JSON.stringify(record),result=estimateFlybys(record,context);
 assert.equal(result.rows.length,3);
 for(let i=0;i<3;i++){assert.ok(Math.abs(result.rows[i].estimated_burn_mps-audit.rows[i].estimated_burn_mps)<1e-3);assert.ok(Math.abs(result.rows[i].mismatch_mps-audit.rows[i].mismatch_mps)<1e-4);}
 assert.ok(Math.abs(result.estimated_powered_flyby_sum_mps-876.4932614)<1e-3);
 assert.ok(Math.abs(result.speed_gap_sum_mps-1147.2119149)<1e-3);
 assert.equal(result.modeled_coast_dsm_mps,0);assert.equal(JSON.stringify(record),before);
});
test('display-table interpolation retains enough accuracy for clearly labeled estimates',()=>{
 const playback=read('docs/data/planet_playback.json'),result=estimateFlybys(record,playback);
 for(let i=0;i<3;i++){assert.ok(Math.abs(result.rows[i].estimated_burn_mps-audit.rows[i].estimated_burn_mps)<2);assert.ok(Math.abs(result.rows[i].mismatch_mps-audit.rows[i].mismatch_mps)<2);}
});
test('missing JPL dates produce an unavailable estimate rather than a fabricated zero burn',()=>{
 const result=estimateFlybys(record,{bodies:{}});assert.equal(result.estimated_powered_flyby_sum_mps,null);assert.equal(result.speed_gap_sum_mps,null);assert.ok(result.rows.every(r=>r.error));
 assert.throws(()=>planetState({states:[[1,1,0,0,0,0,0]]},2),/No cached/);
});
test('changing minimum altitudes affects the construction without moving the saved trajectory',()=>{
 const result=estimateFlybys(record,context,{'399':10000});for(const r of result.rows.filter(r=>r.body==='Earth'))assert.ok(r.estimated_altitude_km>=9999.999);
 assert.throws(()=>poweredGeometry(398600,1e7,[10,0,0],[9,1,0],1e6),/outside/);
});
