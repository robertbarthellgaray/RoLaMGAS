import {state} from './community.js?v=20261116live';
import {planetState,FLYBY_BODIES,storedMismatch} from './flyby_diagnostics.js?v=20261112d';
export function combinedMismatch(candidate,record,context){
 let sum=record?.metrics?.combined_vinf_mismatch_mps??candidate?.combined_mismatch_mps;
 let source='stored sum';
 if(!Number.isFinite(sum)&&candidate?.flybys?.length){const rows=candidate.flybys.map(f=>f.mismatch_mps??f.speed_mismatch_mps);if(rows.every(Number.isFinite)){sum=rows.reduce((a,b)=>a+Math.abs(b),0);source='saved flyby rows';}}
 if(!Number.isFinite(sum)&&record&&context){
  const gaps=[];let complete=true;
  for(let i=1;i<record.body_ids.length-1;i++){
   const name=FLYBY_BODIES[record.body_ids[i]]?.[0];if(!name)continue;
   try{const jd=record.dates_jd_tdb[i],table=context.bodies[name]?.segments.find(s=>s.start<=jd&&s.end>=jd),planet=planetState(table,jd);
    const before=record.segments.find(s=>Math.abs(s.end_jd-jd)<1e-6),after=record.segments.find(s=>Math.abs(s.start_jd-jd)<1e-6);if(!before||!after)throw Error('Missing coast');
    const incoming=state(before.r,before.v,(jd-before.start_jd)*86400)[1].map((v,k)=>v-planet[k+3]),outgoing=after.v.map((v,k)=>v-planet[k+3]);
    gaps.push(Math.abs(Math.hypot(...incoming)-Math.hypot(...outgoing))*1000);
   }catch{complete=false;break;}
  }
  if(complete){sum=gaps.reduce((a,b)=>a+b,0);source='interpolated JPL screen';}
 }
 const peak=storedMismatch(record)??candidate?.validation?.max_vinf_mismatch_mps??candidate?.mismatch_max_mps;
 return {sum_mps:Number.isFinite(sum)?sum:null,red:(Number.isFinite(sum)&&sum>1000+1e-6)||(Number.isFinite(peak)&&peak>1000+1e-6),source:Number.isFinite(sum)?source:'saved maximum lower bound'};
}
