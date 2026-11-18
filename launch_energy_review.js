// Advisory launch-energy comparisons. Never changes trajectory dynamics or burns.
(function(root){
 'use strict';
 const ids={Earth:'399',Venus:'299',Mercury:'199',Mars:'499',Jupiter:'599',Saturn:'699',Uranus:'799',Neptune:'899'};
 const median=a=>{const s=a.slice().sort((a,b)=>a-b),i=Math.floor(s.length/2);return s.length?(s.length%2?s[i]:(s[i-1]+s[i])/2):null;};
 function stats(a){const mean=a.reduce((s,x)=>s+x,0)/a.length;return {n:a.length,mean,median:median(a),stddev:Math.sqrt(a.reduce((s,x)=>s+(x-mean)**2,0)/a.length)};}
 function describe(q,targetId){
  const bodies=q.body_ids||q.bodies||[],sequence=String(q.sequence||'').replace(/dV/g,'dv');
  const target=String(targetId||q.target_id||ids[bodies.at(-1)]||bodies.at(-1)||'');
  const c3=q.metrics?.launch_c3_km2_s2??q.launch_c3_km2_s2??q.c3;
  const years=q.metrics?.duration_years??q.duration_years??q.years;
  const start=q.dates_jd_tdb?.[0]??q.start;
  return {id:q.id,key:JSON.stringify([sequence,String(ids[bodies[0]]||bodies[0]||'399'),target]),sequence,c3,years,start,mga:bodies.length>=3};
 }
 function firstLeg(sequence){const t=sequence.match(/Me|Er|dv|[EVMJSUNPX]/g)||[];return t.slice(0,t[1]==='dv'?3:2).join('');}
 function build(records){
  const groups={};for(const q of records){const d=describe(q);if(!Number.isFinite(d.c3)||!Number.isFinite(d.years)||d.c3<5||d.years<=0)continue;(groups[d.key]??={sequence:d.sequence,first_leg:firstLeg(d.sequence),peers:[]}).peers.push({id:d.id,c3:d.c3,years:d.years,start:d.start});}
  for(const g of Object.values(groups)){g.c3=stats(g.peers.map(p=>p.c3));g.flight_time=stats(g.peers.map(p=>p.years));}
  return {schema_version:1,description:'Search-biased saved candidates, grouped by complete sequence, departure body and target. Not a feasibility boundary.',groups};
 }
 function review(q,reference,targetId){
  const d=describe(q,targetId),g=reference?.groups?.[d.key],high=d.mga&&d.c3>150;
  const enough=g?.c3.n>=5,baseline=enough?g.c3.median:null;
  const extreme=d.c3>150||(enough&&d.c3>=3*baseline&&d.c3-baseline>=40);
  const elevated=extreme||d.c3>=100||(enough&&d.c3>=1.5*baseline&&d.c3-baseline>=10);
  const energy_level=extreme?'extreme':elevated?'high':enough?'usual':'unrated';
  const energy_label=extreme?'Launch energy RIDICULOUSLY HIGH':elevated?'Launch energy relatively high':enough?'Launch energy within usual saved range':'Launch energy: limited comparison data';
  const energy_explanation='Advisory, not a feasibility verdict. High: C3 ≥100, or ≥1.5× the same-route median with ≥10 extra C3. Extreme: C3 >150, or ≥3× the median with ≥40 extra C3. Relative comparisons need five saved routes and may span different launch years. C3 is in km²/s²; launch mass and onboard DSMs are separate.';
  const advisory={energy_level,energy_label,energy_explanation};
  if(!enough)return {...advisory,flagged:false,high_energy:high,first_leg:firstLeg(d.sequence),insufficient_peers:true};
  const unusual=d.c3>g.c3.median+Math.max(20,.75*g.c3.median)||d.c3>g.c3.mean+Math.max(20,3*g.c3.stddev);
  const witness=unusual?g.peers.filter(p=>p.id!==d.id&&p.c3<=.75*d.c3&&d.c3-p.c3>=10&&d.years>=.8*p.years).sort((a,b)=>a.years-b.years||a.c3-b.c3)[0]:null;
  const flagged=Boolean(witness);
  const reason=flagged?`${d.sequence}: unusually high launch C3 without a 20% flight-time improvement over a saved route using at least 25% less C3. Try refining this candidate to minimize C3.`:'';
  return {...advisory,flagged,high_energy:high,first_leg:g.first_leg,statistics:g.c3,flight_time:g.flight_time,witness,reason,scope:'Same complete sequence and target across saved launch years. Different launch windows may be involved; these statistics do not prove a lower-energy solution exists for your chosen dates.'};
 }
 function notice(rows){const mga=rows.map(q=>describe(q)).filter(q=>q.mga),high=mga.filter(q=>q.c3>150);return {show:high.length>=3&&high.length>=.25*mga.length,count:high.length,total:mga.length};}
 const warning='Hold your horses! These trajectories have a huge amount of launch energy. C3 above 150 km²/s² can be useful for a lightweight, fast outer-system flyby, but severely limits launch mass. New Horizons launched at about C3 158, weighed 478 kg, and reached Pluto in about 9.5 years. Select a candidate and refine it with “minimize C3.” Launch injection is separate from onboard DSMs.';
 root.LaunchEnergyReview=Object.freeze({build,review,notice,firstLeg,warning,describe});
})(globalThis);
