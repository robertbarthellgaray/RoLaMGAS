import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {localEnv} from './local_server.mjs';
import {smallBodyQualityReason} from '../docs/library_policy.js';

test('high energy needs a short small-body flight; planets are not constrained',()=>{
 for(const id of ['9','999','20090377','54667839','1000036']){
  assert.ok(smallBodyQualityReason(id,170.001,25));assert.equal(smallBodyQualityReason(id,170,25),null);
  assert.ok(smallBodyQualityReason(id,100,40));assert.equal(smallBodyQualityReason(id,200,24.999),null);
 }
 assert.equal(smallBodyQualityReason('899',200,50),null);
});

test('quality migration backs up exact rows, purges only matching entries and rejects their return',()=>{
 const env=localEnv(),db=env.database;
 const insert=(id,target,years,c3)=>db.prepare('INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)').run(id,target,'EX',2460000,2460000+years*365.25,c3,'pass','2026-01-01','2026-01-01','{"original":true}','2026-01-01','server receipt',id,1);
 insert('long','999',40,100);insert('costly','20090377',25,171);insert('useful','999',24,200);insert('planet','899',50,200);
 const sql=readFileSync(new URL('./migrations/0003_small_body_quality.sql',import.meta.url),'utf8');db.exec(sql);
 assert.deepEqual(db.prepare('SELECT id FROM candidates ORDER BY id').all().map(r=>r.id),['planet','useful']);
 assert.deepEqual(db.prepare('SELECT id,payload FROM quality_purge_20261112 ORDER BY id').all().map(r=>[r.id,r.payload]),[['costly','{"original":true}'],['long','{"original":true}']]);
 db.exec(sql);assert.equal(db.prepare('SELECT COUNT(*) n FROM quality_purge_20261112').get().n,2);
 assert.throws(()=>insert('again','9',40,20),/quality limit/);
 assert.throws(()=>db.prepare('UPDATE candidates SET arrival_jd=launch_jd+14610 WHERE id=?').run('useful'),/quality limit/);
 db.close();
});
