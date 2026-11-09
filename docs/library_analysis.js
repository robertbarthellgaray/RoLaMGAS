// Comparison uses saved costs, not a claim of physical validation.
const DWARFS=new Set(['Pluto','Ceres','Eris','Haumea','Makemake','Sedna']);
const PLANETS=new Set(['Mercury','Venus','Earth','Mars','Jupiter','Saturn','Uranus','Neptune']);
export const CATEGORIES=['Dwarf planets','Asteroids','Comets','Other bodies'];
export function bodyCategory(name,id=''){
 if(PLANETS.has(name))return 'Planets';
 if(DWARFS.has(name)||['999','20000001','20136199','20136108','20136472','20090377','20225088'].includes(String(id)))return 'Dwarf planets';
 if((Number(id)>=1000000&&Number(id)<2000000)||/^(?:[CPADX]\/|\d+[PD]\/)/i.test(name))return 'Comets';
 if(Number(id)>=2000000||['Arrokoth','624 Hektor','13579 Allodd','420356 Praamzius','2026 ED138','2012 VP113'].includes(name))return 'Asteroids';
 return 'Other bodies';
}
export function encounterDayKey(record){
 if(!record?.body_ids||!record?.dates_jd_tdb)return null;
 return JSON.stringify([record.body_ids.map(String),record.dates_jd_tdb.map(jd=>Math.floor(jd+.5))]);
}
export function duplicateRank(record){const m=record.metrics;return [record.classification==='pass'?0:1,m.launch_c3_km2_s2/100+m.total_dsm_kms+m.arrival_vinf_kms/20+(record.dates_jd_tdb.at(-1)-record.dates_jd_tdb[0])/365.25/100,String(record.id)]}
export function betterDuplicate(a,b){const x=duplicateRank(a),y=duplicateRank(b);for(let i=0;i<x.length;i++)if(x[i]!==y[i])return x[i]<y[i];return false}
export function launchYear(row){return new Date((row.start-2440587.5)*86400000).getUTCFullYear()}
export function filteredYears(rows,min,max){return rows.filter(r=>launchYear(r)>=min&&launchYear(r)<=max)}
export function sequenceColors(rows){const names=[...new Set(rows.map(r=>r.sequence))].sort();return new Map(names.map((s,i)=>[s,`hsl(${Math.round(i*360/Math.max(1,names.length))} 72% 69%)`]))}
export function resolveAlias(id,aliases){const seen=new Set();while(aliases[id]&&!seen.has(id)){seen.add(id);id=aliases[id]}return id}

export function filterStateFromHash(hash){const p=new URLSearchParams(hash.replace(/^#/,'')),year=key=>{const s=p.get(key);return s!==null&&/^\d{1,6}$/.test(s)?s:''};return {target:p.get('target'),mission:p.get('mission'),launchMin:year('launch_from'),launchMax:year('launch_to')}}
export function filterHash(state){const p=new URLSearchParams();if(state.target&&state.target!=='All')p.set('target',state.target);if(state.mission)p.set('mission',state.mission);for(const [key,value]of [['launch_from',state.launchMin],['launch_to',state.launchMax]])if(value!==''&&value!=null&&/^\d{1,6}$/.test(String(value)))p.set(key,value);return '#'+p}

export function missionFiltersFromHash(hash){
 const p=new URLSearchParams(hash.replace(/^#/,'')),out={metric:p.get('axis')==='vinf'?'vinf':'c3'};
 for(const [key,param] of [['maxYears','max_years'],['maxC3','max_c3'],['maxVinf','max_vinf'],['maxBurns','max_burns']]){const v=p.get(param);out[key]=v!==null&&v.trim()!==''&&Number.isFinite(Number(v))&&Number(v)>=0?v:'';}
 return out;
}
export function withMissionFilters(hash,state){
 const p=new URLSearchParams(hash.replace(/^#/,''));if(state.metric==='vinf')p.set('axis','vinf');
 for(const [key,param] of [['maxYears','max_years'],['maxC3','max_c3'],['maxVinf','max_vinf'],['maxBurns','max_burns']]){const v=state[key];if(v!==''&&v!=null&&Number.isFinite(Number(v))&&Number(v)>=0)p.set(param,v);}
 return '#'+p;
}
