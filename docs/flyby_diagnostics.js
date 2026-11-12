// Analytic diagnostics only: never modifies saved burns, controls or trajectories.
import {state,bodyName} from './community.js?v=20261112d';
const AU=149597870.7,DAY=86400,MU=132712440041.27942;
export const FLYBY_BODIES=Object.freeze({
 '199':['Mercury',22031.86855,2439.7,200],'299':['Venus',324858.592,6051.8,300],
 '399':['Earth',398600.435436,6378.137,200],'499':['Mars',42828.375816,3396.19,200],
 '599':['Jupiter',126686531.9,71492,10000],'699':['Saturn',37931206.234,60268,10000],
 '799':['Uranus',5793950.6103,25559,1000],'899':['Neptune',6835099.5,24764,1000]
});
const norm=v=>Math.hypot(...v),dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0),sub=(a,b)=>a.map((x,i)=>x-b[i]);
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
export function storedMismatch(record){const value=record?.metrics?.max_vinf_mismatch_mps;return Number.isFinite(value)&&value>=0?value:null;}
export function planetState(table,jd){
 const rows=table?.states;
 if(!rows?.length||jd<rows[0][0]||jd>rows.at(-1)[0])throw Error('No cached JPL context for this encounter date');
 if(rows.length===1)return rows[0].slice(1).map((v,i)=>v*AU/(i<3?1:DAY));
 let lo=0,hi=rows.length-1;while(hi-lo>1){const m=(lo+hi)>>1;if(rows[m][0]<=jd)lo=m;else hi=m;}
 const a=rows[lo],b=rows[hi],dt=b[0]-a[0],t=(jd-a[0])/dt;
 const h=[2*t**3-3*t*t+1,t**3-2*t*t+t,-2*t**3+3*t*t,t**3-t*t];
 const d=[(6*t*t-6*t)/dt,3*t*t-4*t+1,(-6*t*t+6*t)/dt,3*t*t-2*t];
 return [...[0,1,2].map(i=>(h[0]*a[1+i]+h[1]*dt*a[4+i]+h[2]*b[1+i]+h[3]*dt*b[4+i])*AU),
  ...[0,1,2].map(i=>(d[0]*a[1+i]+d[1]*a[4+i]+d[2]*b[1+i]+d[3]*b[4+i])*AU/DAY)];
}
export function poweredGeometry(mu,minimumRadius,incoming,outgoing,maximumRadius){
 const ni=norm(incoming),no=norm(outgoing);
 if(Math.min(ni,no)<1e-8)throw Error('Degenerate flyby speed');
 const a=incoming.map(x=>x/ni),b=outgoing.map(x=>x/no),c=Math.max(-1,Math.min(1,dot(a,b))),normal=cross(a,b),s=norm(normal);
 if(s<1e-10)throw Error('Degenerate common-periapsis geometry');
 const angle=Math.atan2(s,c),natural=r=>Math.asin(1/(1+r*ni*ni/mu))+Math.asin(1/(1+r*no*no/mu));
 let radius=minimumRadius;
 if(!(maximumRadius>radius))throw Error('Minimum periapsis is outside the planetary patch');
 if(angle<natural(radius)){
  if(angle<natural(maximumRadius))throw Error('Required periapsis is outside the planetary patch');
  let lo=radius,hi=maximumRadius;for(let i=0;i<85;i++){const mid=(lo+hi)/2;if(natural(mid)>angle)lo=mid;else hi=mid;}radius=(lo+hi)/2;
 }
 const si=1/(1+radius*ni*ni/mu),so=1/(1+radius*no*no/mu),x=(si+c*so)/(1-c*c),y=(-so-c*si)/(1-c*c);
 const p0=a.map((v,i)=>x*v+y*b[i]),lengthSquared=dot(p0,p0);
 if(lengthSquared>1+1e-8)throw Error('No common periapsis above this altitude floor');
 let p=p0.map((v,i)=>v+Math.sqrt(Math.max(0,1-lengthSquared))*normal[i]/s);const pn=norm(p);p=p.map(v=>v/pn);
 const vi=a.map((v,i)=>Math.sqrt(ni*ni+2*mu/radius)*(v-si*p[i])/Math.sqrt(1-si*si));
 const vo=b.map((v,i)=>Math.sqrt(no*no+2*mu/radius)*(v+so*p[i])/Math.sqrt(1-so*so)),delta=sub(vo,vi);
 return {periapsis_radius_km:radius,delta_v_vector_kms:delta,magnitude_mps:norm(delta)*1000};
}
export function estimateFlybys(record,ephemerides,floors={}){
 const rows=[];
 for(let i=1;i<record.body_ids.length-1;i++){
  const id=record.body_ids[i],jd=record.dates_jd_tdb[i],constants=FLYBY_BODIES[id],row={body:bodyName(id),jd};
  rows.push(row);
  try{
   if(!constants)throw Error('Gravity model unavailable for this encounter body');
   const [body,mu,radius,defaultFloor]=constants,floor=floors[id]??defaultFloor;
   if(!Number.isFinite(floor)||floor<0)throw Error('Enter a nonnegative minimum altitude');
   const table=ephemerides.bodies[body]?.segments.find(s=>s.start<=jd&&jd<=s.end),planet=planetState(table,jd);
   const before=record.segments.find(s=>Math.abs(s.end_jd-jd)<1e-6),after=record.segments.find(s=>Math.abs(s.start_jd-jd)<1e-6);
   if(!before||!after)throw Error('Saved encounter coasts unavailable');
   const incoming=sub(state(before.r,before.v,(jd-before.start_jd)*DAY)[1],planet.slice(3)),outgoing=sub(after.v,planet.slice(3));
   row.mismatch_mps=Math.abs(norm(incoming)-norm(outgoing))*1000;row.minimum_altitude_km=floor;
   const power=poweredGeometry(mu,radius+floor,incoming,outgoing,.799*norm(planet.slice(0,3))*(mu/MU)**.4);
   Object.assign(row,{estimated_burn_mps:power.magnitude_mps,estimated_altitude_km:power.periapsis_radius_km-radius,delta_v_vector_kms:power.delta_v_vector_kms});
  }catch(error){row.error=error.message;}
 }
 let dsm=0;
 for(const control of record.dsm_controls){const a=record.dates_jd_tdb[control.leg_index],b=record.dates_jd_tdb[control.leg_index+1],jd=a+(b-a)*control.fraction;
  const before=record.segments.find(s=>Math.abs(s.end_jd-jd)<1e-6),after=record.segments.find(s=>Math.abs(s.start_jd-jd)<1e-6);
  if(!before||!after){dsm=null;break;}dsm+=norm(sub(after.v,state(before.r,before.v,(jd-before.start_jd)*DAY)[1]))*1000;
 }
 return {rows,speed_gap_sum_mps:rows.every(r=>Number.isFinite(r.mismatch_mps))?rows.reduce((s,r)=>s+r.mismatch_mps,0):null,
  estimated_powered_flyby_sum_mps:rows.every(r=>Number.isFinite(r.estimated_burn_mps))?rows.reduce((s,r)=>s+r.estimated_burn_mps,0):null,
  modeled_coast_dsm_mps:dsm,note:'Conservative common-periapsis construction using interpolated JPL display context. These are estimates, not optimized burns or a finite-radius integrated trajectory. Original modeled burns are unchanged.'};
}
