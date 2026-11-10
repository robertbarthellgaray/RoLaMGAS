// A selected trajectory plus portable search settings, not a screenshot or run path.
const ids={Mercury:'199',Venus:'299',Earth:'399',Mars:'499',Jupiter:'599',Saturn:'699',Uranus:'799',Neptune:'899'};
const iso=jd=>new Date((jd-2440587.5)*86400000).toISOString().replace(/Z$/,'');
export function transferDocument(c,label=''){
 let record=c.community_record||c.desktop_record||null;
 const dates=record?.dates_jd_tdb||c.events.map(e=>e.jd),bodies=c.bodies,target=bodies.at(-1);
 const controls=record?.dsm_controls||[],branches=record?.branches;
 // Public notation may use P/Er for readability; desktop custom targets use X.
 const tokens={Mercury:'Me',Venus:'V',Earth:'E',Mars:'M',Jupiter:'J',Saturn:'S',Uranus:'U',Neptune:'N'};
 const sequence=!ids[target]&&record?bodies.map((b,i)=>(tokens[b]||'X')+(controls.some(d=>d.leg_index===i)?'dv':'')).join(''):c.sequence;
 if(record&&sequence!==record.sequence)record={...record,sequence};
 const box=Math.max(5,...controls.flatMap(b=>b.departure_offset_kms.map(x=>Math.abs(x)+.01)));
 const modeledDsm=(c.burns||[]).filter(b=>b.kind==='DSM').reduce((sum,b)=>sum+b.magnitude_mps,0);
 const powered=c.powered_flybys===true||(c.flybys||[]).some(f=>f.powered_mps>0)||(Boolean(record)&&c.burns_mps-modeledDsm>1);
 const settings={target,sequences:[sequence],launch_start:iso(dates[0]),launch_end:iso(dates[0]),event_windows:dates.map(jd=>[iso(jd),iso(jd)]),min_c3:6.25,max_c3:Math.max(200,c.c3+1),max_years:Math.max(30,c.years+.1),max_dsm_kms:Math.max(1.5,c.burns_mps/1000+.01),max_single_dsm_kms:.7,max_powered_flyby_kms:.2,max_arrival_vinf_kms:Math.max(15,c.vinf+.1),vinf_tolerance_mps:20,dsm_velocity_box_kms:box,search_objective:'feasibility',powered_flybys:false,minimum_altitude_km:Object.fromEntries((c.flybys||[]).filter(f=>f.altitude_floor_km!=null).map(f=>[f.body,f.altitude_floor_km]))};
 if(!ids[target]){
  const id=record?.body_ids?.at(-1)||c.target_id||c.provenance?.target_horizons_id;
  if(!id)throw Error('Target identity missing; use this trajectory’s data files instead.');
  settings.target_object=c.target_descriptor||{name:target,id:String(id),command:String(id),kind:'horizons_object',query:'SPK='+id};
 }
 settings.powered_flybys=powered;
 if(!record){delete settings.event_windows;settings.launch_end=iso(dates[0]+1);settings.arrival_date=iso(c.end);settings.arrival_tolerance_days=1;}
 if(branches)settings.route_overrides={[sequence]:{leg_days:dates.slice(1).map((d,i)=>[Math.max(1,(d-dates[i])*.5),(d-dates[i])*1.5+1]),branch_options:branches.map(b=>[b])}};
 return {format:'rolamgas-search-options',schema_version:1,app_version:'0.2.4-test3',settings,...(record?{trajectory:record}:{}),display_name:String(label||c.title||c.sequence).slice(0,100),source_candidate_id:c.id};
}
export function finiteRadiusDownload(c){return c.model==='Integrated concept'||c.model==='Patched-conic export'||c.trajectory_files?.finite_radius===true;}
