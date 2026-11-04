// Public science records only. No IP, account, cookie or device identifier is read or stored.
const KEYS=['schema_version','engine_version','sequence','body_ids','dates_jd_tdb','branches','dsm_controls','classification','solved_at','metrics','segments','id'];
const METRICS=['launch_c3_km2_s2','total_dsm_kms','arrival_vinf_kms','duration_years','max_vinf_mismatch_mps'];
function number(value,min,max){if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max)throw Error('Invalid numeric field');return value;}
function exact(value,keys){if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!keys.includes(k)))throw Error('Unknown record field');}
function vector(v,limit){if(!Array.isArray(v)||v.length!==3)throw Error('Invalid vector');return v.map(n=>number(n,-limit,limit));}
function canonical(v){if(Array.isArray(v))return v.map(canonical);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])]));return v;}
// The public slot groups encounter calendar days, independent of Lambert branches
// or sub-day optimizer noise. Keep exact science IDs in payloads for old clients.
export function encounterKey(record){return record.body_ids.join('/')+'@'+record.dates_jd_tdb.map(jd=>Math.floor(jd+.5)).join('/');}
export function selectionScore(record){const m=record.metrics,d=record.dates_jd_tdb;return m.launch_c3_km2_s2/100+m.total_dsm_kms+m.arrival_vinf_kms/20+(d.at(-1)-d[0])/365.25/100;}
export async function validate(input){
 exact(input,KEYS);
 if(input.schema_version!==1||!['pass','yellow'].includes(input.classification))throw Error('Only pass/yellow science records are accepted');
 if(!/^(?:Me|dv|dV|[EVMJSUNX]){2,30}$/.test(input.sequence))throw Error('Invalid sequence');
 if(typeof input.engine_version!=='string'||!/^[0-9A-Za-z.+-]{1,32}$/.test(input.engine_version))throw Error('Invalid engine version');
 const ids=input.body_ids,dates=input.dates_jd_tdb,branches=input.branches;
 if(!Array.isArray(ids)||ids.length<2||ids.length>16||!ids.every(v=>typeof v==='string'&&/^-?\d{1,12}$/.test(v)))throw Error('Invalid body IDs');
 if(!Array.isArray(dates)||dates.length!==ids.length)throw Error('Invalid epochs');
 dates.forEach((n,i)=>{number(n,2300000,2700000);if(i&&n<=dates[i-1])throw Error('Unordered epochs');});
 const target=Number(ids.at(-1));if((target===999||target>=1000)&&(dates.at(-1)-dates[0])/365.25>=60)throw Error('Small-body flight time must be below 60 years');
 if(!Array.isArray(branches)||branches.length!==ids.length-1)throw Error('Invalid branches');
 branches.forEach(b=>{if(!Array.isArray(b)||![2,3].includes(b.length)||!Number.isInteger(b[0])||b[0]<0||b[0]>16||typeof b[1]!=='boolean'||(b.length===3&&typeof b[2]!=='boolean'))throw Error('Invalid branch');});
 if(!Array.isArray(input.dsm_controls)||input.dsm_controls.length>ids.length-1)throw Error('Invalid DSM controls');
 let previous=-1;
 const controls=input.dsm_controls.map(d=>{exact(d,['leg_index','fraction','departure_offset_kms']);if(!Number.isInteger(d.leg_index)||d.leg_index<=previous||d.leg_index>=ids.length-1)throw Error('Invalid DSM leg');previous=d.leg_index;return {leg_index:d.leg_index,fraction:number(d.fraction,.1,.9),departure_offset_kms:vector(d.departure_offset_kms,1000)};});
 exact(input.metrics,METRICS);const metrics=Object.fromEntries(METRICS.map(k=>[k,number(input.metrics[k],0,1e9)]));
 if(metrics.launch_c3_km2_s2>250)throw Error('Public library C3 exceeds 250 km2/s2');
 const time=Date.parse(input.solved_at);if(typeof input.solved_at!=='string'||input.solved_at.length>40||!Number.isFinite(time)||time<0||time>Date.now()+86400000)throw Error('Invalid solve time');
 if(!Array.isArray(input.segments)||input.segments.length<1||input.segments.length>32)throw Error('Invalid segments');
 const segments=input.segments.map(s=>{exact(s,['start_jd','end_jd','r','v']);number(s.start_jd,dates[0]-.001,dates.at(-1)+.001);number(s.end_jd,s.start_jd+1e-8,dates.at(-1)+.001);return {start_jd:s.start_jd,end_jd:s.end_jd,r:vector(s.r,1e13),v:vector(s.v,10000)};});
 const key={sequence:input.sequence,body_ids:ids,dates_jd_tdb:dates,branches,dsm_controls:controls};
 const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(canonical(key))));
 const id=Array.from(new Uint8Array(digest),n=>n.toString(16).padStart(2,'0')).join('');
 return {...key,schema_version:1,engine_version:input.engine_version,classification:input.classification,solved_at:new Date(time).toISOString(),metrics,segments,id};
}
function headers(origin){return {'Content-Type':'application/json; charset=utf-8','Access-Control-Allow-Origin':origin||'*','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':'Content-Type','Vary':'Origin','X-Content-Type-Options':'nosniff'};}
function response(value,status=200,origin='',extra={}){return new Response(JSON.stringify(value),{status,headers:{...headers(origin),...extra}});}
export default {async fetch(request,env){
 const origin=request.headers.get('Origin')||'';
 const allowed=(env.ALLOWED_ORIGINS||'').split(',').map(s=>s.trim());
 const local=/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(origin);
 if(origin&&!allowed.includes(origin)&&!local)return response({error:'Origin not allowed'},403);
 if(request.method==='OPTIONS')return new Response(null,{status:204,headers:headers(origin)});
 const url=new URL(request.url);
 try {
  if(url.pathname==='/v1/health')return response({service:'RoLaMGAS community library',schema_version:1,stores_identity:false},200,origin);
  if(url.pathname!=='/v1/candidates')return response({error:'Not found'},404,origin);
  if(request.method==='POST'){
   if(!request.headers.get('Content-Type')?.startsWith('application/json'))return response({error:'JSON required'},415,origin);
   const declared=Number(request.headers.get('Content-Length')||0);if(declared>256000)return response({error:'Batch too large'},413,origin);
   // Bound streaming input too; a missing Content-Length cannot bypass the cap.
   const reader=request.body?.getReader();if(!reader)return response({error:'Empty body'},400,origin);
   const chunks=[];let size=0;
   for(;;){const {value,done}=await reader.read();if(done)break;size+=value.byteLength;if(size>256000){await reader.cancel();return response({error:'Batch too large'},413,origin);}chunks.push(value);}
   const bytes=new Uint8Array(size);let offset=0;for(const b of chunks){bytes.set(b,offset);offset+=b.length;}
   const body=JSON.parse(new TextDecoder().decode(bytes));exact(body,['candidates']);
   if(!Array.isArray(body.candidates)||!body.candidates.length||body.candidates.length>10)throw Error('Submit 1 to 10 candidates');
   const records=await Promise.all(body.candidates.map(validate));
   const now=new Date().toISOString(),day=now.slice(0,10),limit=Math.min(5000,Math.max(1,Number(env.MAX_DAILY_CANDIDATES)||5000));
   if(records.length>limit)return response({error:'Daily submission budget reached; try tomorrow'},429,origin);
   const budget=await env.DB.prepare('INSERT INTO daily_budget(day,submissions) VALUES(?1,?2) ON CONFLICT(day) DO UPDATE SET submissions=submissions+excluded.submissions WHERE submissions+excluded.submissions<=?3 RETURNING submissions').bind(day,records.length,limit).first();
   if(!budget)return response({error:'Daily submission budget reached; try tomorrow'},429,origin);
   // A unique encounter slot makes concurrent old/new client submissions safe.
   // A better representative atomically replaces the previous one and refreshes
   // received_at so incremental website readers can update the same-day slot.
   const sql=`INSERT INTO candidates(id,target,sequence,launch_jd,arrival_jd,c3,classification,solved_at,received_at,payload,encounter_key,selection_score)
    VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12)
    ON CONFLICT(encounter_key) DO UPDATE SET
     id=excluded.id,target=excluded.target,sequence=excluded.sequence,launch_jd=excluded.launch_jd,
     arrival_jd=excluded.arrival_jd,c3=excluded.c3,classification=excluded.classification,
     solved_at=excluded.solved_at,received_at=excluded.received_at,payload=excluded.payload,
     selection_score=excluded.selection_score
    WHERE (excluded.classification='pass' AND candidates.classification='yellow')
     OR (excluded.classification=candidates.classification AND
      (excluded.selection_score<candidates.selection_score OR
       (excluded.selection_score=candidates.selection_score AND excluded.id<candidates.id)))`;
   for(const r of records)await env.DB.prepare(sql).bind(r.id,r.body_ids.at(-1),r.sequence,r.dates_jd_tdb[0],r.dates_jd_tdb.at(-1),r.metrics.launch_c3_km2_s2,r.classification,r.solved_at,now,JSON.stringify(r),encounterKey(r),selectionScore(r)).run();
   return response({accepted:records.length,ids:records.map(r=>r.id)},200,origin);
  }
  if(request.method==='GET'){
   const p=url.searchParams,target=p.get('target')||'599';if(target!=='all'&&!/^-?\d{1,12}$/.test(target))throw Error('Invalid target ID');
   const lo=number(Number(p.get('min_c3')??0),0,1e9),hi=number(Number(p.get('max_c3')??1e9),lo,1e9);
   const a=number(Number(p.get('launch_start')??2300000),2300000,2700000),b=number(Number(p.get('launch_end')??2700000),a,2700000);
   const count=Math.floor(number(Number(p.get('limit')??50),1,100));
   const since=p.get('since')||'1970-01-01T00:00:00.000Z';
   const iso=value=>typeof value==='string'&&value.length===24&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString()===value;
   if(!iso(since))throw Error('Invalid since timestamp');
   const values=[lo,hi,a,b,since],where=['c3>=?1','c3<=?2','launch_jd>=?3','launch_jd<=?4','received_at>=?5'];
   const vinf=number(Number(p.get('max_arrival_vinf')??1e9),0,1e9),years=number(Number(p.get('max_years')??1e9),0,1e9);
   values.push(vinf);where.push("json_extract(payload,'$.metrics.arrival_vinf_kms')<=?"+values.length);
   values.push(years);where.push("json_extract(payload,'$.metrics.duration_years')<=?"+values.length);
   if(target!=='all'){values.push(target);where.push('target=?'+values.length)}
   if(p.has('cursor')){
    const cursor=JSON.parse(p.get('cursor'));
    if(!Array.isArray(cursor)||cursor.length!==2||!iso(cursor[0])||typeof cursor[1]!=='string'||!/^[a-f0-9]{64}$/.test(cursor[1]))throw Error('Invalid cursor');
    values.push(cursor[0],cursor[1]);const t=values.length-1,i=values.length;
    where.push(`(received_at<?${t} OR (received_at=?${t} AND id>?${i}))`);
   }
   values.push(count+1);
   const rows=await env.DB.prepare('SELECT id,payload,received_at FROM candidates WHERE '+where.join(' AND ')+' ORDER BY received_at DESC,id LIMIT ?'+values.length).bind(...values).all();
   const page=rows.results.slice(0,count),last=page.at(-1),next=rows.results.length>count?JSON.stringify([last.received_at,last.id]):null;
   return response({schema_version:1,verification:'Submitted classifications are unverified. Recompute locally before use.',server_time:new Date().toISOString(),next_cursor:next,candidates:page.map(r=>({...JSON.parse(r.payload),received_at:r.received_at}))},200,origin,{'Cache-Control':'public, max-age=60'});
  }
  return response({error:'Method not allowed'},405,origin);
 }catch(error){return response({error:error.message==='Unknown record field'?'Only the documented public science fields are allowed':'Invalid request or temporarily unavailable library'},400,origin);}
}};
