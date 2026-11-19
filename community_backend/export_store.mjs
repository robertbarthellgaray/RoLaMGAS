// Numeric science exports only. No arbitrary archives or local file uploads.
const HEX=/^[a-f0-9]{64}$/,encoder=new TextEncoder();
const reportFields=new Set(['exported_launch_c3_km2_s2','total_onboard_delta_v_kms','patch_join_delta_v_kms','passes_original_onboard_budget','passes_individual_burn_limits','post_flyby_months','arrival_altitude_option_km','arrival_inclination_option_deg','numerical_validation_passed','clearance_screen_passed','export_kind','force_model','moon_body','target_mode']);
const json=(value,status=200)=>Response.json(value,{status});
async function bounded(stream,max){if(!stream)throw Error('Empty export');const chunks=[];let size=0;const reader=stream.getReader();for(;;){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>max){await reader.cancel();throw Error('Export size limit exceeded');}chunks.push(value);}const result=new Uint8Array(size);let offset=0;for(const part of chunks){result.set(part,offset);offset+=part.length;}return result;}
async function digest(bytes){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');}
function exact(obj,allowed){if(!obj||typeof obj!=='object'||Array.isArray(obj)||Object.keys(obj).some(k=>!allowed.includes(k)))throw Error('Unknown export field');}
export async function checkExport(data,validate){
 exact(data,['schema_version','source','validation','states','burns']);if(data.schema_version!==1)throw Error('Unsupported export');
 const source=await validate(data.source),v=data.validation;exact(v,[...reportFields]);
 if(v.numerical_validation_passed!==true||v.clearance_screen_passed!==true||!['planet','moon'].includes(v.export_kind))throw Error('Export requires numeric and clearance checks');
 if(!Number.isFinite(v.exported_launch_c3_km2_s2)||v.exported_launch_c3_km2_s2<5||v.exported_launch_c3_km2_s2>250||!Number.isFinite(v.total_onboard_delta_v_kms)||v.total_onboard_delta_v_kms<0)throw Error('Require actual export C3 and maneuver cost');
 for(const [key,value] of Object.entries(v)){if(typeof value==='number'&&(!Number.isFinite(value)||Math.abs(value)>1e10))throw Error('Invalid validation value');if(typeof value==='string'&&(!/^[A-Za-z0-9 _.,;:+()/-]{1,200}$/.test(value)||value.includes('\\')))throw Error('Invalid public description');if(!['number','string','boolean'].includes(typeof value))throw Error('Invalid validation type');}
 if(!Array.isArray(data.states)||data.states.length<2||data.states.length>100000)throw Error('Invalid state count');
 for(let i=0;i<data.states.length;i++){const row=data.states[i];if(!Array.isArray(row)||row.length!==7||!row.every(Number.isFinite)||row[0]<2e6||row[0]>3e6||(i&&row[0]<=data.states[i-1][0])||row.slice(1,4).some(v=>Math.abs(v)>1e13)||row.slice(4).some(v=>Math.abs(v)>10000))throw Error('Invalid state vector');}
 if(!Array.isArray(data.burns)||data.burns.length>1000)throw Error('Invalid burn count');
 for(const row of data.burns){exact(row,['kind','julian_date_tdb','magnitude_kms','dx_kms','dy_kms','dz_kms']);if(!/^[A-Za-z][A-Za-z0-9 _+().-]{0,99}$/.test(row.kind)||Object.entries(row).some(([k,v])=>k!=='kind'&&(!Number.isFinite(v)||Math.abs(v)>3e6)))throw Error('Invalid maneuver');}
 return {...data,source};
}
export async function exportStore(request,env,validate,encounterKey){
 const url=new URL(request.url),candidate=url.searchParams.get('candidate');
 if(!env.EXPORTS)return request.method==='GET'?json({storage_ready:false,exports:[]}):json({error:'Export storage is not enabled yet. Your local export is saved.'},503);
 if(url.pathname==='/v1/exports'&&request.method==='GET'){
  if(!HEX.test(candidate||''))return json({error:'Use a candidate ID'},400);
  const list=await env.EXPORTS.list({prefix:'exports/'+candidate+'/',limit:50,include:['customMetadata']});
  return json({storage_ready:true,exports:list.objects.map(o=>JSON.parse(o.customMetadata.summary)),truncated:list.truncated});
 }
 if(url.pathname==='/v1/exports'&&request.method==='POST'){
  if(request.headers.get('Content-Type')!=='application/gzip')return json({error:'Use a gzip numeric export'},415);
  const compressed=await bounded(request.body,6000000),stream=new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'));
  const data=await checkExport(JSON.parse(new TextDecoder().decode(await bounded(stream,12000000))),validate);
  const linked=await env.DB.prepare('SELECT id FROM candidates WHERE id=?1 OR encounter_key=?2 LIMIT 1').bind(data.source.id,encounterKey(data.source)).first();
  if(!linked)return json({error:'Share the source candidate first'},409);
  const hash=await digest(encoder.encode(JSON.stringify(data))),key='exports/'+linked.id+'/'+hash+'.json.gz';
  if(await env.EXPORTS.head(key))return json({candidate_id:linked.id,export_id:hash,duplicate:true});
  const day='exports:'+new Date().toISOString().slice(0,10),limit=Number(env.MAX_DAILY_EXPORTS)||100;
  const budget=await env.DB.prepare('INSERT INTO daily_budget(day,submissions) VALUES(?1,1) ON CONFLICT(day) DO UPDATE SET submissions=submissions+1 WHERE submissions<?2 RETURNING submissions').bind(day,limit).first();
  if(!budget)return json({error:'Daily export sharing budget reached; local export remains available'},429);
  const summary={candidate_id:linked.id,source_id:data.source.id,export_id:hash,added_at:new Date().toISOString(),rows:data.states.length,start:data.states[0][0],end:data.states.at(-1)[0][0],...data.validation};
  const canonical=encoder.encode(JSON.stringify(data)),gzip=await new Response(new Blob([canonical]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();
  await env.EXPORTS.put(key,gzip,{httpMetadata:{contentType:'application/gzip'},customMetadata:{summary:JSON.stringify(summary)}});
  return json({candidate_id:linked.id,export_id:hash});
 }
 const match=url.pathname.match(/^\/v1\/exports\/([a-f0-9]{64})\/([a-f0-9]{64})\/(trajectory\.xyzv|trajectory\.csv|validation\.json|burns\.csv)$/);
 if(request.method!=='GET'||!match)return json({error:'Export not found'},404);
 const object=await env.EXPORTS.get('exports/'+match[1]+'/'+match[2]+'.json.gz');if(!object)return json({error:'Export not found'},404);
 const data=JSON.parse(new TextDecoder().decode(await bounded(object.body.pipeThrough(new DecompressionStream('gzip')),12000000))),file=match[3];let body;
 if(file==='validation.json')body=JSON.stringify({source_id:data.source.id,source:data.source,validation:data.validation,rows:data.states.length,start:data.states[0][0],end:data.states.at(-1)[0][0],note:'Submitted numeric export and client validation; not independently propagated by the server.'},null,2);
 else if(file==='burns.csv'){const keys=['kind','julian_date_tdb','magnitude_kms','dx_kms','dy_kms','dz_kms'];body=keys.join(',')+'\n'+data.burns.map(r=>keys.map(k=>r[k]??'').join(',')).join('\n')+'\n';}
 else{const csv=file.endsWith('.csv');body=(csv?'julian_date_tdb,x_km,y_km,z_km,vx_kms,vy_kms,vz_kms\n':'')+data.states.map(r=>r.map(v=>v.toPrecision(17)).join(csv?',':' ')).join('\n')+'\n';}
 return new Response(body,{headers:{'Content-Type':file.endsWith('.json')?'application/json':file.endsWith('.csv')?'text/csv':'application/octet-stream','Content-Disposition':'attachment; filename="rolamgas-'+match[1].slice(0,12)+'-'+match[2].slice(0,8)+'-'+file+'"','Cache-Control':'public, max-age=31536000, immutable','X-Content-Type-Options':'nosniff'}});
}
