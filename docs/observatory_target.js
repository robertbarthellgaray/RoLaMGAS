// Preview context only. Never invent time-dependent small-body ephemerides.
export const MAJOR_PLANETS=new Set(['Mercury','Venus','Earth','Mars','Jupiter','Saturn','Uranus','Neptune']);
export function targetContext(mission,jd,position){
 const name=mission?.target;if(!name||MAJOR_PLANETS.has(name))return null;
 const event=mission.events?.findLast(e=>e.body===name)||mission.events?.at(-1);
 const dated=position?.(name,jd),point=dated||event?.position_au;
 if(!Array.isArray(point)||point.length!==3||!point.every(Number.isFinite))return null;
 const orbit=mission.planet_paths?.find(p=>p.body===name)?.points;
 return {name,point,dated:Boolean(dated),label:name+(dated?'':' · at encounter'),orbit,
  radiusAU:Math.min(.06,Math.max(.004,Math.hypot(...point)*.002))};
}
