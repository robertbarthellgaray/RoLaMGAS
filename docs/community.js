// Live data refreshes independently of GitHub Pages deployments.
const el=id=>document.getElementById(id),MU=132712440041.27942,AU=149597870.7;
function stump(z){if(Math.abs(z)<.1){let c=.5,s=1/6,tc=c,ts=s;for(let k=1;k<=12;k++){tc*=-z/((2*k+1)*(2*k+2));ts*=-z/((2*k+2)*(2*k+3));c+=tc;s+=ts}return [c,s]}if(z>0){const s=Math.sqrt(z);return [2*(Math.sin(s/2)/s)**2,(s-Math.sin(s))/s**3]}const s=Math.sqrt(-z);if(s>600)throw Error('Overflow');return [(Math.cosh(s)-1)/-z,(Math.sinh(s)-s)/s**3]}
export function state(r,v,dt){if(!dt)return [r.slice(),v.slice()];const radius=Math.hypot(...r),root=Math.sqrt(MU),rv=r.reduce((a,x,i)=>a+x*v[i],0)/root,alpha=2/radius-v.reduce((a,x)=>a+x*x,0)/MU;let lo=0,hi=Math.max(root*dt/radius,1);if(alpha< -1e-14){const l=1/Math.sqrt(-alpha);hi=Math.max(l*Math.asinh(root*dt/(radius*l)),1)}let c,s,value;for(let i=0;i<80;i++){[c,s]=stump(alpha*hi*hi);value=rv*hi*hi*c+(1-alpha*radius)*hi**3*s+radius*hi-root*dt;if(value>=0)break;hi*=2;if(i===79)throw Error('No bracket')}let x=(lo+hi)/2;for(let i=0;i<120;i++){const z=alpha*x*x;[c,s]=stump(z);value=rv*x*x*c+(1-alpha*radius)*x**3*s+radius*x-root*dt;if(Math.abs(value)<Math.max(root*1e-6,Math.abs(root*dt)*4e-14)||hi-lo<Math.max(1e-10,Math.abs(x)*1e-13))break;if(value>0)hi=x;else lo=x;const derivative=rv*x*(1-z*s)+(1-alpha*radius)*x*x*c+radius,trial=x-value/derivative;x=lo<trial&&trial<hi?trial:(lo+hi)/2;if(i===119)throw Error('No convergence')}const f=1-x*x*c/radius,g=dt-x**3*s/root,result=r.map((a,i)=>f*a+g*v[i]),rr=Math.hypot(...result),fdot=root/(radius*rr)*(alpha*x**3*s-x),gdot=1-x*x*c/rr;return [result,r.map((a,i)=>fdot*a+gdot*v[i])]}

export function position(r,v,dt){return state(r,v,dt)[0]}
export const bodyNames={'9':'Pluto','20090377':'Sedna','20136108':'Haumea','20136472':'Makemake','1000036':'1P/Halley','199':'Mercury','299':'Venus','399':'Earth','499':'Mars','599':'Jupiter','699':'Saturn','799':'Uranus','899':'Neptune','999':'Pluto','20000001':'Ceres','20000624':'624 Hektor','20013579':'13579 Allodd','20136199':'Eris','20420356':'420356 Praamzius','20486958':'Arrokoth','54667839':'2026 ED138','50666516':'2012 VP113'};
export function registerBodyNames(document){for(const [id,row] of Object.entries(document?.bodies||{}))if(String(row.horizons_id)===id&&typeof row.name==='string'&&row.name.length<161&&!bodyNames[id])bodyNames[id]=row.name;}
export const bodyName=id=>bodyNames[id]||(Number(id)>=20000000&&Number(id)<30000000?'Asteroid '+(Number(id)-20000000):'Horizons object '+id);
const epoch=jd=>new Date((jd-2440587.5)*86400000).toISOString();
export function missionTiming(record){const dates=record.dates_jd_tdb;if(!Array.isArray(dates)||dates.length<2||!dates.every(Number.isFinite)||dates.at(-1)<=dates[0])throw Error('Invalid mission epochs');const days=dates.at(-1)-dates[0];return {departure:epoch(dates[0]).slice(0,10),arrival:epoch(dates.at(-1)).slice(0,10),days,years:days/365.25}}
export function mergeLibrary(archive,live,target,min=0,max=1e9){const records=new Map();for(const r of [...archive,...live])if(r?.id&&r.body_ids?.at(-1)===target&&r.metrics?.launch_c3_km2_s2>=min&&r.metrics.launch_c3_km2_s2<=max)records.set(r.id,r);return [...records.values()]}
export function summaryFor(record){
 if(record.metrics.launch_c3_km2_s2>250)throw Error('Public library C3 exceeds 250 km2/s2');
 const targetId=Number(record.body_ids.at(-1));if((targetId===9||targetId===999||targetId>=1000)&&missionTiming(record).years>=60)throw Error('Small-body flight time must be below 60 years');
 const t=missionTiming(record),m=record.metrics,bodies=record.body_ids.map(bodyName),target=bodies.at(-1);
 return {id:record.id,target_id:String(record.body_ids.at(-1)),title:record.sequence+' · '+target,target,sequence:record.sequence,bodies,model:'Shared '+record.classification,community:true,classification:record.classification,spotlight:false,start:record.dates_jd_tdb[0],end:record.dates_jd_tdb.at(-1),launch_date:t.departure,arrival_date:t.arrival,years:t.years,c3:m.launch_c3_km2_s2,vinf:m.arrival_vinf_kms,burns_mps:m.total_dsm_kms*1000,received:Date.parse(record.received_at||record.solved_at),added_at:record.added_at,added_at_basis:record.added_at_basis};
}
export function thumbnailFor(record){
 const curves=record.segments.map(s=>Array.from({length:32},(_,j)=>position(s.r,s.v,(s.end_jd-s.start_jd)*86400*j/31).map(x=>x/AU))),pts=[[0,0],...curves.flat()],xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),a=Math.min(...xs),b=Math.max(...xs),c=Math.min(...ys),d=Math.max(...ys),scale=Math.min(290/Math.max(b-a,.1),190/Math.max(d-c,.1));
 const xy=p=>`${(160+(p[0]-(a+b)/2)*scale).toFixed(2)},${(110-(p[1]-(c+d)/2)*scale).toFixed(2)}`;
 const lines=curves.map((line,i)=>`<polyline points="${line.map(xy).join(' ')}" fill="none" stroke="${['#79d8f1','#ffd08a','#8ae3bd','#b4aeff'][i%4]}" stroke-width="1.3"/>`).join('');
 const sun=xy([0,0]).split(',');return 'data:image/svg+xml,'+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="320" height="220" viewBox="0 0 320 220"><rect width="320" height="220" fill="#08121e"/>${lines}<circle cx="${sun[0]}" cy="${sun[1]}" r="3" fill="#ffd08a"/></svg>`);
}
export function caseFor(record){
 const c=summaryFor(record),paths=record.segments.map(s=>{const count=Math.min(400,Math.max(60,Math.ceil((s.end_jd-s.start_jd)/5)));return {start:s.start_jd,end:s.end_jd,times:Array.from({length:count},(_,i)=>s.start_jd+(s.end_jd-s.start_jd)*i/(count-1)),points:Array.from({length:count},(_,i)=>position(s.r,s.v,(s.end_jd-s.start_jd)*86400*i/(count-1)).map(x=>x/AU))}});
 const at=jd=>{const s=record.segments.find(s=>Math.abs(s.start_jd-jd)<1e-7)||record.segments.find(s=>s.start_jd<=jd&&s.end_jd>=jd)||record.segments.at(-1);return position(s.r,s.v,Math.max(0,jd-s.start_jd)*86400).map(x=>x/AU)};
 const events=record.dates_jd_tdb.map((jd,i)=>({body:c.bodies[i],jd,date:epoch(jd).replace('Z',' TDB'),kind:i===0?'Departure':i===c.bodies.length-1?'Arrival':'Flyby / modeled junction',position_au:at(jd)}));
 const burns=record.dsm_controls.map(control=>{const a=record.dates_jd_tdb[control.leg_index],b=record.dates_jd_tdb[control.leg_index+1],jd=a+(b-a)*control.fraction,pre=record.segments.find(s=>Math.abs(s.end_jd-jd)<1e-6),post=record.segments.find(s=>Math.abs(s.start_jd-jd)<1e-6);if(!pre||!post)throw Error('Saved DSM coasts unavailable');const before=state(pre.r,pre.v,(pre.end_jd-pre.start_jd)*86400)[1];return {jd,date:epoch(jd).replace('Z',' TDB'),kind:'DSM',magnitude_mps:Math.hypot(...post.v.map((v,i)=>v-before[i]))*1000,position_au:at(jd)}});
 return {...c,events,burns,flybys:[],paths,planet_paths:[],community_record:record,
 note:'Submitted '+record.classification+' under the original search limits; not independently revalidated. The interactive preview samples the saved Sun-only two-body arcs. Planet-center joins do not model finite-radius flybys. Planet ephemeris context and individual powered-flyby geometry are not included in this public record. The desktop client recomputes the science before reuse. Launch injection and capture are excluded from the displayed cruise budget.',
 provenance:{source:'Shared trajectory library / '+record.engine_version,candidate_id:record.id,coordinates:'Heliocentric Ecliptic J2000',time_scale:'TDB',plot_units:'AU',target_horizons_id:record.body_ids.at(-1),planet_arcs:'Encounter markers only; full planet ephemerides are not included'}};
}
export function trajectoryRows(record,stepDays=2){
 const rows=[];
 for(let k=0;k<record.segments.length;k++){
  const s=record.segments[k],days=s.end_jd-s.start_jd,stop=s.end_jd-(k<record.segments.length-1?1e-7:0),n=Math.min(20000,Math.max(1,Math.ceil(days/stepDays)));
  for(let i=0;i<=n;i++){const jd=s.start_jd+(stop-s.start_jd)*i/n,[r,v]=state(s.r,s.v,(jd-s.start_jd)*86400);rows.push([jd,...r,...v])}
 }
 return rows;
}
export function trajectoryText(record,kind){const rows=trajectoryRows(record),header=kind==='csv'?'julian_date_tdb,x_km,y_km,z_km,vx_km_s,vy_km_s,vz_km_s\n':`# RoLaMGAS Sun-only Lambert coasts; planet-center joins, not finite-radius flybys\n# JD(TDB) range ${rows[0][0]} ${rows.at(-1)[0]}\n# JD(TDB) x(km) y(km) z(km) vx(km/s) vy(km/s) vz(km/s)\n`;return header+rows.map(row=>row.map((v,i)=>v.toFixed(i===0?10:9)).join(kind==='csv'?',':' ')).join('\n')+'\n'}
export async function fetchUpdates(endpoint,since,fetcher=fetch){
 const records=[],cursors=new Set();let cursor=null,watermark=since;
 do{
  const q=new URLSearchParams({target:'all',limit:'100',since});if(cursor)q.set('cursor',cursor);
  const response=await fetcher(endpoint+'/v1/candidates?'+q,{cache:'no-store',signal:AbortSignal.timeout(12000)});if(!response.ok)throw Error('Shared library unavailable');const data=await response.json();
  for(const r of data.candidates){records.push(r);if(r.received_at>watermark)watermark=r.received_at}
  cursor=data.next_cursor;if(cursor){if(cursors.has(cursor)||cursors.size>=1000)throw Error('Invalid library pagination');cursors.add(cursor)}
 }while(cursor);
 return {records,watermark};
}
