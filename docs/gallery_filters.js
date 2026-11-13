// Labels describe provenance, not agreement with operational flight dynamics.
export function missionKind(candidate){
 return candidate.mission_kind==='reconstruction'||candidate.historical_match?'reconstruction':'original';
}
export function matchesGallery(candidate,kind='both',sequence=''){
 return (kind==='both'||missionKind(candidate)===kind)&&(!sequence||candidate.sequence===sequence);
}
export function featuredOrder(a,b){
 return (b.featured_priority||0)-(a.featured_priority||0)
  ||Number(Boolean(b.spotlight))-Number(Boolean(a.spotlight))
  ||(b.received||0)-(a.received||0)||a.id.localeCompare(b.id);
}
