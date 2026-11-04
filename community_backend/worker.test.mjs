import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{validate,encounterKey,selectionScore} from './worker.mjs';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {localEnv} from './local_server.mjs';
const record=()=>({schema_version:1,engine_version:'0.2.1-test7',sequence:'EJ',body_ids:['399','599'],dates_jd_tdb:[2460000,2461000],branches:[[0,true]],dsm_controls:[],classification:'pass',solved_at:'2026-01-01T00:00:00Z',metrics:{launch_c3_km2_s2:11,total_dsm_kms:0,arrival_vinf_kms:7,duration_years:2.7,max_vinf_mismatch_mps:0},segments:[{start_jd:2460000,end_jd:2461000,r:[1e8,0,0],v:[0,30,0]}],id:'a'.repeat(64)});
const post=(env,records)=>worker.fetch(new Request('https://example.test/v1/candidates',{method:'POST',headers:{'Content-Type':'application/json','User-Agent':'private computer name','CF-Connecting-IP':'192.0.2.1'},body:JSON.stringify({candidates:records})}),env);
const get=(env,query='target=599&min_c3=10&max_c3=15')=>worker.fetch(new Request('https://example.test/v1/candidates?'+query),env);
test('stores and queries trajectory science without transport identity',async()=>{const env=localEnv();assert.equal((await post(env,[record()])).status,200);const data=await(await get(env)).json();assert.equal(data.candidates.length,1);assert.ok(data.candidates[0].received_at);const raw=JSON.stringify(env.database.prepare('SELECT * FROM candidates').all());assert.ok(!raw.includes('private computer'));assert.ok(!raw.includes('192.0.2.1'));assert.equal((await(await get(env,'target=599&min_c3=12&max_c3=15')).json()).candidates.length,0);env.database.close();});
test('deduplicates repeated science while preserving first solve time',async()=>{const env=localEnv(),a=record();await post(env,[a]);await post(env,[{...a,solved_at:'2026-02-01T00:00:00Z'}]);assert.equal(env.database.prepare('SELECT COUNT(*) AS n FROM candidates').get().n,1);assert.match((await(await get(env)).json()).candidates[0].solved_at,/2026-01-01/);env.database.close();});
test('rejects personal extra fields, red records, malformed numbers and hostile targets',async()=>{const env=localEnv();for(const a of [{...record(),username:'someone'},{...record(),classification:'red'},{...record(),metrics:{...record().metrics,launch_c3_km2_s2:null}}])assert.equal((await post(env,[a])).status,400);assert.equal((await get(env,"target=599%27%20OR%201=1")).status,400);assert.equal(env.database.prepare('SELECT COUNT(*) AS n FROM candidates').get().n,0);env.database.close();});
test('daily global budget bounds writes without storing visitor identifiers',async()=>{const env=localEnv(':memory:','1');assert.equal((await post(env,[record(),record()])).status,429);assert.equal((await post(env,[record()])).status,200);assert.equal((await post(env,[record()])).status,429);env.database.close();});
test('denies unexpected browser origins',async()=>{const env=localEnv();const response=await worker.fetch(new Request('https://example.test/v1/candidates',{headers:{Origin:'https://unrelated.example'}}),env);assert.equal(response.status,403);env.database.close();});

test('all-target incremental feed paginates without gaps or duplicate records',async()=>{
 const env=localEnv(),a=record(),b={...record(),body_ids:['399','699'],dates_jd_tdb:[2460000,2461100]},c={...record(),dates_jd_tdb:[2460000,2461200]};
 await post(env,[a,b,c]);let cursor=null,ids=[];
 do{const q=new URLSearchParams({target:'all',limit:'1',since:'1970-01-01T00:00:00.000Z'});if(cursor)q.set('cursor',cursor);const page=await(await get(env,q.toString())).json();assert.equal(page.candidates.length,1);ids.push(page.candidates[0].id);cursor=page.next_cursor;}while(cursor);
 assert.equal(ids.length,3);assert.equal(new Set(ids).size,3);
 assert.equal((await(await get(env,'target=all&since=2099-01-01T00%3A00%3A00.000Z')).json()).candidates.length,0);
 assert.equal((await get(env,'target=all&cursor=garbage')).status,400);env.database.close();
});

test('public C3 ceiling retains exactly 250 and rejects anything higher',async()=>{const env=localEnv();const a=record();a.metrics.launch_c3_km2_s2=250;assert.equal((await post(env,[a])).status,200);a.metrics.launch_c3_km2_s2=250.000001;assert.equal((await post(env,[a])).status,400);assert.equal(env.database.prepare('SELECT COUNT(*) AS n FROM candidates').get().n,1);env.database.close()});

test('database-first query filters arrival speed and flight duration',async()=>{const env=localEnv();await post(env,[record()]);assert.equal((await(await get(env,'target=599&max_arrival_vinf=6')).json()).candidates.length,0);assert.equal((await(await get(env,'target=599&max_years=2')).json()).candidates.length,0);assert.equal((await(await get(env,'target=599&max_arrival_vinf=7&max_years=2.7')).json()).candidates.length,1);env.database.close()});

test('small-body 60-year limit uses epochs, preserving shorter trips and planetary tours',async()=>{const env=localEnv(),a=record();a.body_ids=['399','999'];a.dates_jd_tdb=[2460000,2460000+60*365.25];a.segments[0].end_jd=a.dates_jd_tdb[1];a.metrics.duration_years=1;assert.equal((await post(env,[a])).status,400);a.dates_jd_tdb[1]-=.001;a.segments[0].end_jd=a.dates_jd_tdb[1];assert.equal((await post(env,[a])).status,200);a.body_ids=['399','599'];a.dates_jd_tdb[1]+=.001;a.segments[0].end_jd=a.dates_jd_tdb[1];assert.equal((await post(env,[a])).status,200);env.database.close()});

function shifted(a,days){const r=structuredClone(a);r.dates_jd_tdb=r.dates_jd_tdb.map(jd=>jd+days);r.segments=r.segments.map(s=>({...s,start_jd:s.start_jd+days,end_jd:s.end_jd+days}));return r;}
test('same-day encounter slot ignores optimizer noise and atomically keeps the best record',async()=>{
 const env=localEnv(),a=record(),b=shifted(a,.2);b.metrics.launch_c3_km2_s2=10;b.branches=[[0,false]];
 await Promise.all([post(env,[a]),post(env,[b])]);let data=await(await get(env)).json();
 assert.equal(data.candidates.length,1);assert.equal(data.candidates[0].metrics.launch_c3_km2_s2,10);
 assert.equal(data.candidates[0].id,(await validate(b)).id);
 const worse=shifted(a,.25);worse.metrics.launch_c3_km2_s2=14;await post(env,[worse]);
 assert.equal(env.database.prepare('SELECT COUNT(*) AS n FROM candidates').get().n,1);
 assert.equal((await(await get(env)).json()).candidates[0].metrics.launch_c3_km2_s2,10);
 const nextDay=shifted(a,.6);await post(env,[nextDay]);
 assert.equal(env.database.prepare('SELECT COUNT(*) AS n FROM candidates').get().n,2);env.database.close();
});
test('same-day representative prefers submitted pass over yellow and keeps distinct body orders',async()=>{
 const env=localEnv(),yellow=record();yellow.classification='yellow';yellow.metrics.launch_c3_km2_s2=1;
 const pass=shifted(record(),.1);await post(env,[yellow,pass]);
 assert.equal((await(await get(env)).json()).candidates[0].classification,'pass');
 const other={...pass,body_ids:['399','699']};await post(env,[other]);
 assert.equal(env.database.prepare('SELECT COUNT(*) AS n FROM candidates').get().n,2);env.database.close();
});
test('legacy database migration uses the same TDB day keys and cost ranking as live submissions',async()=>{
 const db=new DatabaseSync(':memory:');db.exec(`CREATE TABLE candidates(id TEXT PRIMARY KEY,target TEXT NOT NULL,sequence TEXT NOT NULL,launch_jd REAL NOT NULL,arrival_jd REAL NOT NULL,c3 REAL NOT NULL,classification TEXT NOT NULL,solved_at TEXT NOT NULL,received_at TEXT NOT NULL,payload TEXT NOT NULL);`);
 const a=record(),b=shifted(a,.2),c=shifted(a,.6);b.metrics.launch_c3_km2_s2=8;
 const rows=await Promise.all([a,b,c].map(validate));
 for(const r of rows)db.prepare('INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?)').run(r.id,r.body_ids.at(-1),r.sequence,r.dates_jd_tdb[0],r.dates_jd_tdb.at(-1),r.metrics.launch_c3_km2_s2,r.classification,r.solved_at,r.solved_at,JSON.stringify(r));
 db.exec(readFileSync(new URL('./migrations/0001_same_day_encounters.sql',import.meta.url),'utf8'));
 assert.throws(()=>db.prepare('INSERT INTO candidates(id,target,sequence,launch_jd,arrival_jd,c3,classification,solved_at,received_at,payload) VALUES(?,?,?,?,?,?,?,?,?,?)').run('e'.repeat(64),'599','EJ',2460000,2461000,10,'pass','2026-01-01','2026-01-01','{}'),/encounter key/);
 const saved=db.prepare('SELECT * FROM candidates').all();assert.equal(saved.length,2);assert.ok(saved.some(r=>r.id===rows[1].id));
 for(const row of saved){const r=JSON.parse(row.payload);assert.equal(row.encounter_key,encounterKey(r));assert.equal(row.selection_score,selectionScore(r));}
 assert.throws(()=>db.prepare('INSERT INTO candidates SELECT ?,target,sequence,launch_jd,arrival_jd,c3,classification,solved_at,received_at,payload,encounter_key,selection_score FROM candidates LIMIT 1').run('f'.repeat(64)),/UNIQUE/);db.close();
});
