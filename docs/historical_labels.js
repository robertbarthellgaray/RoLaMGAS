const names={'199':'Mercury','299':'Venus','399':'Earth','499':'Mars','599':'Jupiter','699':'Saturn','799':'Uranus','899':'Neptune'};
const day=jd=>Number.isFinite(jd)?new Date((jd-2440587.5)*86400000).toISOString().slice(0,10):'';
export function historicalMatch(candidate,profiles){
 const record=candidate.community_record||candidate.desktop_record||candidate;
 const bodies=record.body_ids?.map(id=>names[String(id)]||String(id))||candidate.bodies;
 const dates=record.dates_jd_tdb?.map(day)||candidate.events?.map(e=>day(e.jd));
 if(!bodies||!dates||dates.length!==bodies.length)return null;
 const match=profiles.find(m=>m.bodies.length===bodies.length&&m.bodies.every((b,i)=>b===bodies[i]&&m.dates[i]===dates[i]));
 return match?{name:match.name,planned:!!match.planned,label:match.name+(match.planned?' — planned-date match':' — calendar-date match'),sources:match.sources}:null;
}
