// Reversible gallery curation. Original records and direct links remain available.
export const CURATION_RULE = Object.freeze({launchWindowDays:3*365.25, fraction:.20, c3Gain:2, yearsGain:1});
const finite = c => ['start','c3','years','vinf','burns_mps'].every(k=>Number.isFinite(c[k]));
export function familyKey(c){return JSON.stringify([c.target,c.sequence,c.bodies]);}
export function launchMonth(c){return new Date((c.start-2440587.5)*86400000).toISOString().slice(0,7);}
export function launchTimestamp(c){return new Date(Math.round((c.start-2440587.5)*86400)*1000).toISOString().slice(0,19).replace('T',' ')+' TDB';}
export function groupLaunches(rows){
 const groups=new Map();
 for(const c of rows){const key=familyKey(c)+'@'+launchMonth(c);if(!groups.has(key))groups.set(key,{key,sequence:c.sequence,target:c.target,month:launchMonth(c),rows:[]});groups.get(key).rows.push(c);}
 return [...groups.values()]; // Input sorting determines group and variant order.
}
export function clearlyDominates(a,b){
 if(!finite(a)||!finite(b)||familyKey(a)!==familyKey(b)||Math.abs(a.start-b.start)>CURATION_RULE.launchWindowDays)return false;
 return costDominates(a,b);
}
function costDominates(a,b){
 if(a.classification==='yellow'&&b.classification!=='yellow')return false;
 // A cheaper/faster option must also preserve arrival speed and cruise burn cost.
 if(['c3','years','vinf','burns_mps'].some(k=>a[k]>b[k]))return false;
 return b.c3-a.c3>=Math.max(CURATION_RULE.c3Gain,CURATION_RULE.fraction*b.c3)
  ||b.years-a.years>=Math.max(CURATION_RULE.yearsGain,CURATION_RULE.fraction*b.years);
}
export function trimAlternatives(rows,protectedIds=new Set()){
 const families=new Map(),hidden=new Map();
 const eligible=c=>finite(c)&&!c.spotlight&&!/research|integrated/i.test(c.model||'');
 for(const c of rows)if(eligible(c)){const key=familyKey(c);if(!families.has(key))families.set(key,[]);families.get(key).push(c);}
 for(const family of families.values()){
  // Ascending cost gives deterministic witnesses regardless of download order.
  const ranked=family.slice().sort((a,b)=>a.c3-b.c3||a.years-b.years||a.id.localeCompare(b.id));
  for(const b of ranked){
   if(protectedIds.has(b.id))continue;
   const a=ranked.find(a=>a.id!==b.id&&!hidden.has(a.id)&&Math.abs(a.start-b.start)<=CURATION_RULE.launchWindowDays&&costDominates(a,b));
   if(a)hidden.set(b.id,a.id);
  }
 }
 return {rows:rows.filter(c=>!hidden.has(c.id)),hidden};
}
