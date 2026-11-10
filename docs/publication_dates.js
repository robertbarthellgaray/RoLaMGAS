// Publication is distinct from solving a trajectory. Never substitute solved_at.
export function publicationDate(candidate,history={}){
 const record=candidate.community_record||candidate.desktop_record||candidate;
 const historical=history[candidate.id];
 const value=record.added_at||candidate.added_at||historical?.added_at||record.received_at;
 const basis=record.added_at_basis||candidate.added_at_basis||historical?.basis||(record.received_at?'earliest retained receipt':'');
 if(!value||!Number.isFinite(Date.parse(value)))return {text:'Unknown — publication time was not retained',basis:'unavailable'};
 return {text:new Date(value).toISOString().slice(0,19).replace('T',' ')+' UTC',basis};
}
