// Public, geometric target vectors only; no user identifiers or telemetry.
const AU=149597870.7,DAY=86400,MAX_BYTES=3000000;
async function boundedJSON(response,limit=MAX_BYTES){
 if(!response.ok)throw Error('JPL returned HTTP '+response.status);
 const reader=response.body.getReader(),parts=[];let size=0;
 for(;;){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>limit){await reader.cancel();throw Error('JPL response exceeded vector-cache limit');}parts.push(value);}
 const bytes=new Uint8Array(size);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.length;}return JSON.parse(new TextDecoder().decode(bytes));
}
export function parseVectors(text,id,name,designation){
 const header=text.split('$$SOE')[0],section=text.split('$$SOE')[1]?.split('$$EOE')[0];
 if(!section||!header.includes('Center body name: Sun (10)')||!header.includes('GEOMETRIC cartesian states')||!header.includes('Ecliptic of J2000.0')||!header.match(/Output units\s*:\s*AU-D/)||!header.includes('JDTDB'))throw Error('JPL did not return geometric Sun/Ecliptic J2000 AU-D TDB vectors');
 const actual=header.match(/Target body name:\s*([^\n]+)/)?.[1]||'',compact=s=>String(s).replace(/[^a-z0-9]/gi,'').toLowerCase();
 if(!compact(actual).includes(compact(name))&&!(designation&&compact(actual).includes(compact(designation)))&&!actual.includes('('+id+')'))throw Error('JPL target identity differs from the resolved object');
 const states=section.trim().split(/\r?\n/).map(line=>{const cells=line.split(',');return [Number(cells[0]),...cells.slice(2,8).map(x=>x?.trim()?Number(x):NaN)];});
 if(states.length<2||states.length>4000||states.some((r,i)=>r.length!==7||!r.every(Number.isFinite)||(i&&r[0]<=states[i-1][0])))throw Error('Invalid JPL playback vectors');
 return states;
}
export async function targetEphemeris(request,env,ctx,fetcher=fetch,cache=globalThis.caches?.default){
 const url=new URL(request.url),id=url.searchParams.get('target'),block=Number(url.searchParams.get('block'));
 if(request.method!=='GET'||!/^\d{1,12}$/.test(id||'')||!Number.isInteger(block)||block%10||block<1900||block>2190)throw Error('Use a public target ID and a ten-year block from 1900 through 2190');
 const key=new Request(url.origin+'/v1/target-vectors?target='+id+'&block='+block+'&format=1');
 const cached=await cache?.match(key);if(cached)return cached;
 if(!await env.DB.prepare('SELECT 1 AS present FROM candidates WHERE target=?1 LIMIT 1').bind(id).first())return new Response(JSON.stringify({error:'No published trajectory targets this body'}),{status:404,headers:{'Content-Type':'application/json'}});
 const lookup=await boundedJSON(await fetcher('https://ssd.jpl.nasa.gov/api/horizons_lookup.api?'+new URLSearchParams({sstr:id}),{signal:AbortSignal.timeout(25000)}),256000);
 const row=lookup.result?.find(r=>String(r.spkid)===id);if(!row)throw Error('JPL could not resolve the exact public target ID');
 const comet=String(row.type).toLowerCase().includes('comet');
 const start=block+'-01-01',end=(block+10)+'-01-02',startJd=2440587.5+Date.parse(start+'T00:00:00Z')/86400000;
 let command=Number(id)<1000?id:(row.pdes?'DES='+row.pdes+';':id);
 if(comet&&row.pdes)command='DES='+row.pdes+';CAP<'+startJd+';';
 const params={format:'json',COMMAND:"'"+command+"'",EPHEM_TYPE:"'VECTORS'",CENTER:"'500@10'",START_TIME:"'"+start+"'",STOP_TIME:"'"+end+"'",STEP_SIZE:"'1 d'",OUT_UNITS:"'AU-D'",REF_PLANE:"'ECLIPTIC'",REF_SYSTEM:"'ICRF'",VEC_CORR:"'NONE'",VEC_TABLE:"'2'",CSV_FORMAT:"'YES'",TIME_TYPE:"'TDB'"};
 const source='https://ssd.jpl.nasa.gov/api/horizons.api?'+new URLSearchParams(params);
 const data=await boundedJSON(await fetcher(source,{signal:AbortSignal.timeout(25000)}));
 if(data.error)throw Error('JPL: '+String(data.error).slice(0,200));
 const states=parseVectors(data.result||'',id,row.name,row.pdes);
 const response=new Response(JSON.stringify({schema_version:1,target_id:id,name:row.name,block,source,retrieved_at:new Date().toISOString(),frame:'Geometric Sun-centered Ecliptic J2000',time_scale:'TDB',units:'AU and AU/day',segments:[{start:states[0][0],end:states.at(-1)[0],states}],note:'Cubic Hermite display interpolation between daily JPL vectors; not an encounter-targeting ephemeris.'}),{headers:{'Content-Type':'application/json','Cache-Control':'public, max-age=2592000'}});
 if(cache){const saving=cache.put(key,response.clone());if(ctx?.waitUntil)ctx.waitUntil(saving);else await saving;}
 return response;
}
