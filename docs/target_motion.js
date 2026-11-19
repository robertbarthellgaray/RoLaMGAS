export const targetMotion=new Map();
const pending=new Map();
async function storage(){return new Promise(resolve=>{try{const r=indexedDB.open('rolamgas-target-vectors',1);r.onupgradeneeded=()=>r.result.createObjectStore('blocks');r.onsuccess=()=>resolve(r.result);r.onerror=()=>resolve(null);}catch{resolve(null)}});}
async function blockCache(key,value){const db=await storage();if(!db)return null;return new Promise(resolve=>{const tx=db.transaction('blocks',value?'readwrite':'readonly'),store=tx.objectStore('blocks'),r=value?store.put(value,key):store.get(key);r.onsuccess=()=>resolve(value||r.result||null);r.onerror=()=>resolve(null);tx.oncomplete=()=>db.close();});}
export function targetId(c){return String(c?.target_id||c?.provenance?.target_horizons_id||c?.target_descriptor?.id||c?.community_record?.body_ids?.at(-1)||'');}
export function targetPosition(c,body,jd,interpolate){if(body!==c?.target)return null;const table=targetMotion.get(targetId(c));const span=table?.segments.find(s=>s.start<=jd&&s.end>=jd);return span?interpolate(span,jd):null;}
export async function loadTargetMotion(c,endpoint,progress=()=>{}){
 const id=targetId(c);if(!/^\d{1,12}$/.test(id)||!endpoint)return null;
 const first=Math.floor(new Date((c.start-2440587.5)*86400000).getUTCFullYear()/10)*10,last=Math.floor(new Date((c.end-2440587.5)*86400000).getUTCFullYear()/10)*10;
 const packets=[];
 for(let year=first;year<=last;year+=10){
  const key=id+':'+year;progress('Loading '+c.target+' motion · '+year+'–'+(year+10)+'…');
  let packet=await blockCache(key);
  if(!packet){if(!pending.has(key))pending.set(key,(async()=>{const r=await fetch(endpoint+'/v1/target-vectors?'+new URLSearchParams({target:id,block:year}));const data=await r.json();if(!r.ok)throw Error(data.error||'Target vectors unavailable');if(data.target_id!==id||!data.segments?.length)throw Error('Target-vector identity mismatch');await blockCache(key,data);return data;})().finally(()=>pending.delete(key)));packet=await pending.get(key);}
  packets.push(packet);const spans=new Map((targetMotion.get(id)?.segments||[]).map(s=>[s.start,s]));for(const span of packet.segments)spans.set(span.start,span);targetMotion.set(id,{segments:[...spans.values()].sort((a,b)=>a.start-b.start),source:packet.source});
 }
 return targetMotion.get(id);
}
