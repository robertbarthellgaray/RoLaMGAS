import {historicalMatch} from './historical_labels.js?v=20261108b';
import {publicationDate} from './publication_dates.js?v=20261110b';
import {transferDocument,finiteRadiusDownload} from './desktop_transfer.js?v=20261110b';
import './mission_metrics.js?v=20261110a';
import {summaryFor,caseFor,thumbnailFor,trajectoryText,fetchUpdates,bodyName,registerBodyNames} from './community.js?v=20261111a';
import {CATEGORIES,bodyCategory,encounterDayKey,betterDuplicate,launchYear,sequenceColors,registerBodyCategories,resolveAlias,filterStateFromHash,filterHash,missionFiltersFromHash,withMissionFilters} from './library_analysis.js?v=20261108b';
const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (n, digits = 2) => Number(n).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits});
const colors = ['#79d8f1', '#ffd08a', '#8ae3bd', '#b4aeff', '#ff9f9a', '#9ed2ff'];
const catalog = [];
const missionNames=(()=>{try{const data=JSON.parse(localStorage.getItem('rolamgas-mission-names')||'{}');return data&&typeof data==='object'&&!Array.isArray(data)?Object.fromEntries(Object.entries(data).filter(([id,label])=>typeof label==='string'&&label.length<=100)):{}}catch{return {}}})();
let historicalProfiles=[],ownerMissions={},launchPerformance=null,publicationHistory={};
function annotateMission(c,id=c.id){const a=ownerMissions[id];if(a)Object.assign(c,{mission_label:a.label,featured_priority:a.featured_priority,mission_note:a.note});return c;}
function carryMissionLabel(from,to){if(from?.mission_label){Object.assign(to,{mission_label:from.mission_label,mission_note:from.mission_note,featured_priority:from.featured_priority});ownerMissions[to.id]={label:from.mission_label,note:from.mission_note,featured_priority:from.featured_priority};}return to;}
const missionName=c=>missionNames[c.id]||c.mission_label||c.historical_match?.label||(/^(?:Rebuilding|Low-energy|Tianwen|Claudius)/.test(c.title)?c.title:'');
const cache = new Map(), sharedRecords = new Map(), previewCache = new Map(), encounterDays=new Map();
let duplicateAliases={}, displayAliases={}, pendingHashTarget=null;
let sharedEndpoint='', sharedSince='1970-01-01T00:00:00.000Z', sharedBusy=false, curatedAliases={}, visibleCount=48;
let planetEphemerides=null,planetLoad=null,animatePlanets=false;
let destination = 'All', smallBodyTarget = 'All', selected = null, requestVersion = 0, playing = false, lastTick = 0, fraction = 0;
let yaw = -.35, pitch = .65, zoom = 1, view = '3d', framePending = false;
const canvas = $('orbit'), ctx = canvas.getContext('2d');
const bodyColors = {Earth:'#6ea9ff', Venus:'#e3c387', Mercury:'#a7a4a0', Mars:'#e7997e', Jupiter:'#dcc3a6', Saturn:'#f0d28d', Uranus:'#87dfed', Neptune:'#729bff'};

async function fetchJson(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`Could not load saved data (${r.status}). Please retry.`);
  return r.json();
}
const previewHidden={markers:new Set(),orbits:new Set()};
function bodyVisible(body,layer){return $(layer==='orbits'?'planet-arcs':'planet-markers').checked&&!previewHidden[layer].has(body)}
function renderBodyVisibility(c){
 const bodies=[...new Set([...c.events.map(e=>e.body),...c.planet_paths.map(p=>p.body),...movingBodyNames(c)])].filter(Boolean),orbits=new Set([...c.planet_paths.map(p=>p.body),...(planetEphemerides?movingBodyNames(c):[])]);
 $('body-visibility-options').innerHTML=bodies.map(body=>`<div class="body-visibility-row"><span>${escapeHtml(body)}</span><label><input type="checkbox" data-preview-body="${escapeHtml(body)}" data-preview-layer="markers" ${previewHidden.markers.has(body)?'':'checked'}> Body</label><label><input type="checkbox" data-preview-body="${escapeHtml(body)}" data-preview-layer="orbits" ${previewHidden.orbits.has(body)?'':'checked'} ${orbits.has(body)?'':'disabled'}> Orbit${orbits.has(body)?'':' (unavailable)'}</label></div>`).join('');
}
function category(c){return bodyCategory(c.target,c.target_id)}
function makeDestinations() {
  const targets = ['All', 'Mercury', 'Venus', ...(catalog.some(c=>c.target==='Earth')?['Earth']:[]), 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune', ...CATEGORIES.filter(t=>t!=='Other bodies'||catalog.some(c=>category(c)===t))];
  $('destinations').innerHTML = targets.map(t => {
    const n = catalog.filter(c => targetMatches(c, t)).length;
    return `<button type="button" data-target="${escapeHtml(t)}" aria-pressed="${t === destination}">${escapeHtml(t)}<span>${n}</span></button>`;
  }).join('');
  const grouped=CATEGORIES.includes(destination);
  $('small-body-options').hidden = !grouped;
  $('small-body-options').innerHTML = ['All',...new Set(catalog.filter(c=>targetMatches(c)).map(c=>c.target))].map(t => `<button type="button" data-small-body="${escapeHtml(t)}" aria-pressed="${smallBodyTarget===t}">${t==='All'?'All '+escapeHtml(destination.toLowerCase()):escapeHtml(t)}</button>`).join('');
}
function targetMatches(c, t = destination) {
  return t === 'All' || (CATEGORIES.includes(t) ? category(c)===t : c.target === t);
}
function maximum(id) {
  const value = $(id).value.trim();
  return value === '' ? Infinity : Math.max(0, Number(value));
}
function syncGraphYears(){for(const suffix of ['min','max'])$('chart-launch-year-'+suffix).value=$('launch-year-'+suffix).value;}
function minimumYear(){return $('launch-year-min').value.trim()===''?-Infinity:Number($('launch-year-min').value)}
function maximumYear(){return $('launch-year-max').value.trim()===''?Infinity:Number($('launch-year-max').value)}
function targetRows(){return catalog.filter(c=>targetMatches(c)&&(!CATEGORIES.includes(destination)||smallBodyTarget==='All'||c.target===smallBodyTarget))}
function visibleRows(){
 const search=$('search').value.trim().toLowerCase().replace(/\s+/g,'');
 return targetRows().filter(c=>`${missionName(c)} ${c.id} ${c.title} ${c.sequence} ${c.bodies.join(' ')} ${c.launch_date} ${c.arrival_date}`.toLowerCase().replace(/\s+/g,'').includes(search)
  &&(!c.community||c.classification!=='yellow'||$('include-yellow').checked)&&c.c3<=maximum('max-c3')&&c.vinf<=maximum('max-vinf')&&c.burns_mps<=maximum('max-burns')&&c.years<=maximum('max-years')&&launchYear(c)>=minimumYear()&&launchYear(c)<=maximumYear());
}
function renderList() {
  const rows=visibleRows(),sort=$('sort').value;
  rows.sort((a,b) => sort === 'recommended' ? (b.featured_priority || 0) - (a.featured_priority || 0) || Number(b.spotlight) - Number(a.spotlight) || (b.received||0)-(a.received||0) : sort==='received'?(b.received||0)-(a.received||0):a[sort]-b[sort]);
  $('result-count').textContent = `${rows.length} ${rows.length === 1 ? 'trajectory' : 'trajectories'}`;
  $('candidate-more').hidden=visibleCount>=rows.length;
  $('candidate-more').textContent=`Show ${Math.min(48,Math.max(0,rows.length-visibleCount))} more (${Math.min(visibleCount,rows.length)} of ${rows.length})`;
  $('candidate-list').innerHTML = rows.length ? rows.slice(0,visibleCount).map(c => `<button type="button" class="candidate-card" data-id="${c.id}" aria-pressed="${c.id === selected?.id}" aria-label="Inspect ${escapeHtml(c.title)}, launch ${c.launch_date}, C3 ${fmt(c.c3)}">
    <div class="card-preview"><img loading="lazy" src="${c.community ? sharedPreview(c.id) : `images/${c.id}.svg`}" width="320" height="220" alt="${escapeHtml(c.sequence)} heliocentric trajectory preview"><span class="card-badge">${c.spotlight ? 'Integrated concept' : escapeHtml(c.model)}</span></div>
    <div class="card-title">${escapeHtml(missionName(c)||c.sequence)}<b aria-hidden="true">↗</b></div><p class="card-subtitle">${escapeHtml(c.target)} · ${c.launch_date} → ${c.arrival_date}</p>
    <div class="card-metrics"><div><span>C3 · km²/s²</span>${fmt(c.c3,1)}</div><div><span>Δv · m/s</span>${fmt(c.burns_mps,0)}</div><div><span>FLIGHT · yr</span>${fmt(c.years,1)}</div></div></button>`).join('')
    : '<p class="empty">No saved examples match these filters. Try raising a limit, changing launch years or choosing another destination.</p>';
  drawTradeoff(rows);
  if (rows.length && !rows.some(c => c.id === selected?.id)) selectCandidate(rows[0].id);
}
function selectedTarget(){return CATEGORIES.includes(destination)?(smallBodyTarget==='All'?null:smallBodyTarget):destination==='All'?null:destination}
function drawTradeoff(rows=visibleRows()){
 const target=selectedTarget(),chart=$('tradeoff-chart');
 if(!target){chart.hidden=true;$('tradeoff-status').textContent='Choose a planet or a named small body to compare its trajectories.';return}
 chart.hidden=false;
 if(!rows.length){$('tradeoff-svg').innerHTML='';$('tradeoff-legend').innerHTML='';$('tradeoff-status').textContent=minimumYear()>maximumYear()?'The first launch year must be at or before the last year.':'No trajectories match this target and launch-year range.';return}
 const all=targetRows(),vertical=c=>$('chart-metric').value==='vinf'?c.vinf:c.c3,verticalLabel=$('chart-metric').value==='vinf'?'Arrival V∞ (km/s)':'Launch C3 (km²/s²)';
 const palette=sequenceColors(all),w=1000,h=340,left=74,right=22,top=22,bottom=56,maxX=Math.max(.1,...rows.map(c=>c.years))*1.06,maxY=Math.max(.1,...rows.map(vertical))*1.08;
 let svg='';
 for(let i=0;i<=5;i++){const x=left+(w-left-right)*i/5,y=h-bottom-(h-top-bottom)*i/5;svg+=`<path d="M${x},${top}V${h-bottom}M${left},${y}H${w-right}" stroke="#26394a" stroke-width="1"/><text x="${x}" y="${h-bottom+22}" text-anchor="middle">${fmt(maxX*i/5,1)}</text><text x="${left-10}" y="${y+4}" text-anchor="end">${fmt(maxY*i/5,maxY<1?2:1)}</text>`}
 svg+=`<text class="axis-label" x="${(left+w-right)/2}" y="${h-5}" text-anchor="middle">Flight time (years)</text><text class="axis-label" transform="translate(17 ${(top+h-bottom)/2}) rotate(-90)" text-anchor="middle">${verticalLabel}</text>`;
 svg+=rows.map(c=>`<circle class="tradeoff-point" data-candidate="${escapeHtml(c.id)}" tabindex="0" role="button" aria-pressed="${c.id===selected?.id}" aria-label="${escapeHtml(c.sequence)}, launch ${c.launch_date}, C3 ${fmt(c.c3)}, ${fmt(c.years)} years, arrival V∞ ${fmt(c.vinf)} km/s; open trajectory and downloads" cx="${left+c.years/maxX*(w-left-right)}" cy="${h-bottom-vertical(c)/maxY*(h-top-bottom)}" r="5" fill="${palette.get(c.sequence)}"><title>${escapeHtml(c.sequence)} · launch ${c.launch_date} · C3 ${fmt(c.c3)} km²/s² · ${fmt(c.years,3)} years · arrival V∞ ${fmt(c.vinf,3)} km/s</title></circle>`).join('');
 $('tradeoff-svg').innerHTML=svg;$('tradeoff-svg').setAttribute('aria-label',`Flight time versus ${verticalLabel}; select a point to inspect and download`);
 $('tradeoff-legend').innerHTML=[...palette].filter(([sequence])=>rows.some(c=>c.sequence===sequence)).map(([sequence,color])=>`<span><i class="sequence-swatch" style="background:${color}"></i>${escapeHtml(sequence)}</span>`).join('');
 $('tradeoff-status').textContent=`${target} · ${rows.length} trajectories · ${Math.min(...rows.map(launchYear))}–${Math.max(...rows.map(launchYear))} launches. Select a dot to inspect and download.`;
}


function updateParkingEstimate(){
 if(!selected)return;
 const estimate=globalThis.MissionMetrics.parkingInjection(selected.c3,Number($('parking-altitude').value),selected.bodies[0]);
 $('parking-delta-v').textContent=estimate?`Ideal departure Δv: ${fmt(estimate.deltaVKms,4)} km/s from a ${fmt(estimate.altitudeKm,1)} km circular ${estimate.body} orbit. C3 ${fmt(selected.c3,3)} km²/s².`:'Enter a positive altitude above a supported departure planet.';
}
function renderLaunchPerformance(){
 if(!selected||!$('launch-performance-table'))return;
 const rows=globalThis.MissionMetrics.launchCapacities(launchPerformance,selected.c3);
 $('launch-performance-status').textContent=rows.length?'C3 '+fmt(selected.c3,3)+' km²/s² · NASA data retrieved '+launchPerformance.retrieved_at.slice(0,10)+'. Values between samples are interpolated estimates; blank capacity means no cached coverage.':'NASA capacity data is unavailable for this selection.';
 const body=rows.map(r=>'<tr><td>'+escapeHtml(r.vehicle)+'</td><td>'+(r.capacity_kg==null?'—':(r.interpolated?'≈ ':'')+fmt(r.capacity_kg,0))+'</td><td>'+escapeHtml(r.launch_site)+'</td></tr>').join('');
 const rules=rows.map(r=>'<p><strong>'+escapeHtml(r.vehicle)+'</strong> · '+escapeHtml(r.ground_rules)+'</p>').join('');
 $('launch-performance-table').innerHTML=rows.length?'<div class="table-scroll"><table><thead><tr><th>Vehicle / configuration</th><th>Capacity · kg</th><th>Launch site</th></tr></thead><tbody>'+body+'</tbody></table></div><details><summary>Vehicle ground rules</summary>'+rules+'</details>':'';
}
function renderSequenceComparison(){
 if(!selected)return;
 const stats=globalThis.MissionMetrics.compare(catalog,selected);
 if(stats.n<2){$('sequence-statistics').textContent=`Only ${stats.n} matching saved candidate${stats.n===1?'':'s'}. At least two are needed for comparison.`;return;}
 const rows=[['c3','C3 · km²/s²',selected.c3],['years','Flight · years',selected.years],['vinf','Arrival V∞ · km/s',selected.vinf]];
 $('sequence-statistics').innerHTML=`<p class="quiet">${stats.n} saved candidates · ${escapeHtml(selected.sequence)} · ${escapeHtml(selected.target)}</p><table><thead><tr><th>Metric</th><th>Selected</th><th>Mean</th><th>Median</th><th>σ</th><th>Percentile</th></tr></thead><tbody>${rows.map(([key,label,value])=>{const d=stats[key];return d?`<tr><td>${label}</td><td>${fmt(value,3)}</td><td>${fmt(d.mean,3)}</td><td>${fmt(d.median,3)}</td><td>${fmt(d.stddev,3)}</td><td>${fmt(d.percentile,1)}%</td></tr>`:''}).join('')}</tbody></table>`;
}
function movingBodyNames(c){return [...new Set(c.bodies)].filter(body=>bodyColors[body]);}
function planetPosition(body,jd){
 const segment=planetEphemerides?.bodies[body]?.segments.find(s=>s.start<=jd&&jd<=s.end);
 return globalThis.MissionMetrics.ephemerisPosition(segment,jd);
}
function attachPlanetContext(c){
 if(!planetEphemerides)return;
 // Shared records contain no planet context. Add sampled JPL orbit arcs for display only.
 for(const body of movingBodyNames(c)){
  if(c.planet_paths.some(p=>p.body===body))continue;
  const table=planetEphemerides.bodies[body],middle=(c.start+c.end)/2;
  const segment=table?.segments.find(s=>s.start<=middle&&middle<=s.end);if(!segment)continue;
  const start=Math.max(segment.start,middle-table.period_days/2),end=Math.min(segment.end,middle+table.period_days/2);
  c.planet_paths.push({body,points:Array.from({length:300},(_,i)=>planetPosition(body,start+(end-start)*i/299))});
 }
}
function updateAnimationStatus(){
 if(!selected)return;
 if(!animatePlanets){$('planet-animation-status').textContent='Play the spacecraft alone, or animate planets at the same TDB epoch.';return;}
 const missing=movingBodyNames(selected).filter(body=>!planetPosition(body,currentJd()));
 $('planet-animation-status').textContent=missing.length?`No cached JPL playback coverage for ${missing.join(', ')} at this date; those moving markers are omitted. Encounter markers remain fixed.`:'Planets and spacecraft share the timeline’s TDB date. JPL planet positions are interpolated for display; fixed markers show encounter locations.';
}
async function togglePlanetAnimation(){
 if(animatePlanets){animatePlanets=false;$('animate-planets').textContent='Animate planets';$('animate-planets').setAttribute('aria-pressed','false');updateAnimationStatus();drawSoon();return;}
 const button=$('animate-planets');button.disabled=true;$('planet-animation-status').textContent='Loading compact JPL planet playback data…';
 try{
  if(!planetLoad)planetLoad=fetchJson('data/planet_playback.json?v=20261110a').catch(error=>{planetLoad=null;throw error});
  planetEphemerides=await planetLoad;animatePlanets=true;button.textContent='Planets animated ✓';button.setAttribute('aria-pressed','true');
  if(selected){attachPlanetContext(selected);renderBodyVisibility(selected);$('planet-arcs').disabled=false;$('planet-arcs').title='Dated JPL ephemeris context, interpolated for display';updateAnimationStatus();if(fraction>=1)fraction=0;setPlaying(true);updateTime();}
 }catch(error){$('planet-animation-status').textContent='Planet animation unavailable: '+error.message;}
 finally{button.disabled=false;drawSoon();}
}
$('save-mission-name').addEventListener('click',()=>{if(!selected)return;const name=$('mission-name').value.trim();if(name.length>100||/[\u0000-\u001f\u007f]/.test(name)){$('mission-name-status').textContent='Use at most 100 characters, without control characters.';return;}if(name)missionNames[selected.id]=name;else delete missionNames[selected.id];try{localStorage.setItem('rolamgas-mission-names',JSON.stringify(missionNames));$('mission-name-status').textContent=name?'Saved. Search this name in the trajectory library.':'Custom name cleared.';$('mission-title').textContent=name||selected.title;renderList()}catch{$('mission-name-status').textContent='Browser storage unavailable; name is retained for this visit only.';}});
$('apply-historical-name').addEventListener('click',()=>{if(!selected?.historical_match)return;$('mission-name').value=selected.historical_match.label;$('save-mission-name').click();});
$('parking-altitude').addEventListener('input',updateParkingEstimate);
$('animate-planets').addEventListener('click',togglePlanetAnimation);
function canonicalId(id){return resolveAlias(id,{...duplicateAliases,...curatedAliases,...displayAliases})}
function updateLocation(id){const hash=withMissionFilters(filterHash({target:selectedTarget()||destination,mission:id,launchMin:$('launch-year-min').value,launchMax:$('launch-year-max').value}),{metric:$('chart-metric').value,maxYears:$('max-years').value,maxC3:$('max-c3').value,maxVinf:$('max-vinf').value,maxBurns:$('max-burns').value});history.replaceState(null,'',`${location.pathname}${location.search}${hash}`)}
function applyTargetHash(target){if(!target)return false;if(CATEGORIES.includes(target)||target==='All'||Object.keys(bodyColors).includes(target)){destination=target;smallBodyTarget='All';return true}const row=catalog.find(c=>c.target===target);if(row){destination=category(row);smallBodyTarget=target;return true}return false}
function setPlaying(value) {
  playing = value;
  $('play').textContent = value ? 'Ⅱ' : '▶';
  $('play').setAttribute('aria-label', value ? 'Pause trajectory' : 'Play trajectory');
  if (value) { lastTick = performance.now(); requestAnimationFrame(tick); }
}
function julianDate(jd) {
  return new Date((jd - 2440587.5) * 86400000).toISOString().slice(0, 10);
}
function currentJd() { return selected ? selected.start + fraction * (selected.end - selected.start) : 0; }
function updateTime() {
  updateAnimationStatus();
  $('time').value = Math.round(fraction * 1000);
  $('clock').textContent = selected ? julianDate(currentJd()) : '—';
  drawSoon();
}
function tick(now) {
  if (!playing) return;
  fraction = Math.min(1, fraction + (now - lastTick) / 35000); lastTick = now;
  updateTime();
  if (fraction >= 1) setPlaying(false); else requestAnimationFrame(tick);
}
async function selectCandidate(id) {
  id=canonicalId(id);
  const token = ++requestVersion;
  setPlaying(false);
  $('mission-view').setAttribute('aria-busy', 'true');
  for (const name of ['download-csv','download-xyzv','download-state-readme']) { $(name).hidden=true; $(name).removeAttribute('href'); }
  $('trajectory-download-note').textContent='';
  $('plot-message').hidden = false; $('plot-message').textContent = 'Loading saved flight…';
  try {
    let c = cache.get(id);
    if (!c) { c = sharedRecords.has(id) ? caseFor(sharedRecords.get(id)) : await fetchJson(`data/cases/${encodeURIComponent(id)}.json?v=20261110d`); cache.set(id, c); }
    if (token !== requestVersion) return;
    annotateMission(c);selected = c; attachPlanetContext(c); renderBodyVisibility(c); fraction = 0; zoom = 1; setView('3d');
    updateLocation(c.id);
    document.querySelectorAll('[data-candidate]').forEach(p=>p.setAttribute('aria-pressed',p.dataset.candidate===c.id));
    $('model-label').textContent = c.model.toUpperCase();
    c.historical_match=historicalMatch(c,historicalProfiles);
    $('mission-title').textContent = missionName(c)||c.title;$('mission-name').value=missionNames[c.id]||'';
    $('apply-historical-name').hidden=!c.historical_match;
    $('mission-name-status').textContent=c.historical_match?c.historical_match.label+'. Every encounter calendar day matches; spacecraft vectors and burns are not validated.':'Save a searchable name in this browser. No complete historical calendar-date match was found.';
    $('mission-dates').textContent = `${c.launch_date} → ${c.arrival_date} (TDB) · ${fmt(c.years,3)} years / ${fmt(c.end-c.start,1)} days · ${c.bodies.join(' → ')}`;
    $('mission-id').textContent = c.id;
    const publication=publicationDate(c,publicationHistory);
    $('mission-added').textContent='Added to repository: '+publication.text;
    $('mission-added').title='Source: '+publication.basis+'. First encounter-sequence publication is retained when a better same-day candidate replaces it.';
    const metrics = [ ['Launch C3', fmt(c.c3), 'km²/s²'], ['Cruise Δv', fmt(c.burns_mps,1), 'm/s'], ['Arrival V∞', fmt(c.vinf), 'km/s'], ['Flight time', fmt(c.years), 'years'] ];
    $('metrics').innerHTML = metrics.map(([label,value,unit]) => `<div class="metric"><p>${label}</p><strong>${value}</strong><small>${unit}</small></div>`).join('');
    const events = [...c.events.map(e => ({...e, burn:false})), ...c.burns.filter(globalThis.MissionMetrics.visibleManeuver).map(b => ({...b, burn:true}))].sort((a,b) => a.jd - b.jd);
    $('events').innerHTML = events.map(e => {
      const f = c.flybys.find(f => Math.abs(f.jd - e.jd) < .0001);
      let detail = e.burn ? `${fmt(e.magnitude_mps,2)} m/s` : e.kind;
      if (e.altitude_km != null) detail += ` · ${fmt(e.altitude_km,0)} km altitude`;
      if (f) detail = `${fmt(f.altitude_km,0)} km inferred altitude · ${fmt(f.mismatch_mps,3)} m/s |ΔV∞|${f.powered_mps ? ` · ${fmt(f.powered_mps,1)} m/s powered` : ''}`;
      return `<tr><td><i class="event-dot ${e.burn?'burn-dot':''}"></i>${escapeHtml(e.burn ? e.kind : e.body)}</td><td>${escapeHtml(e.date.replace('T',' ').replace(/\.[0-9]+(?= TDB)/,'').replace(' TDB',''))}</td><td>${e.jd.toFixed(6)}</td><td>${escapeHtml(detail)}</td></tr>`;
    }).join('');
    $('model-note').textContent = [c.mission_note,c.note].filter(Boolean).join(' ');renderLaunchPerformance();updateParkingEstimate();renderSequenceComparison();updateAnimationStatus();
    const labels = {source:'Data source', coordinates:'Coordinates', time_scale:'Time scale', plot_units:'Preview units', candidate_id:'Candidate', speed_tolerance_mps:'Saved speed tolerance (m/s)', sha256:'XYZV SHA-256', export_units:'Export columns', ephemerides:'Ephemerides', planet_arcs:'Planet context',target_horizons_id:'Horizons target ID',target_ephemeris:'Target representation'};
    $('provenance').innerHTML = Object.entries(labels).filter(([key]) => c.provenance[key] != null).map(([key,label]) => `<dt>${label}</dt><dd>${escapeHtml(c.provenance[key])}</dd>`).join('');
    if(c.validation) {
      const v=c.validation;
      $('provenance').innerHTML += `<dt>Gallery admission</dt><dd>${v.passed?'Passed independent vector and coast checks':'Not admitted'}</dd><dt>Worst |ΔV∞|</dt><dd>${fmt(v.max_vinf_mismatch_mps,6)} m/s ${c.powered_flybys?'(powered joins audited from full periapsis vectors)':'(unpowered limit 1 m/s)'}</dd><dt>Largest DSM</dt><dd>${fmt(v.max_single_dsm_mps,3)} m/s (limit 700 m/s)</dd><dt>Coast endpoint error</dt><dd>${fmt(v.max_coast_endpoint_error_km*1000,3)} m maximum</dd>`;
    }
    if(c.integration_validation) {
      $('provenance').innerHTML += `<dt>JPL clearance audit</dt><dd>Passed · Sun and eight planetary surfaces</dd><dt>Audit scope</dt><dd>${escapeHtml(c.integration_validation.scope)}</dd>`;
    }
    $('planet-arcs').disabled=Boolean(c.community)&&!planetEphemerides;
    $('planet-arcs').title=c.community&&!planetEphemerides?'Enable planet animation to load dated JPL context.':'';
    const files = c.trajectory_files,finite=finiteRadiusDownload(c);
    $('download-csv').textContent=finite?'Trajectory CSV ↓':'Lambert analysis CSV ↓';
    $('download-xyzv').textContent='Flyby trajectory XYZV ↓';
    for (const [name,key] of [['download-csv','csv'],['download-xyzv','xyzv'],['download-state-readme','readme'],['download-integration-report','integration_report'],['download-burns','burns']]) {
      const link=$(name); link.hidden=!files?.[key];
      if(files?.[key]) link.href=files[key];
    }
    if(files) $('trajectory-download-note').textContent=`${files.rows.toLocaleString()} saved position/velocity states · ${files.units} · ${files.coordinates}. ${files.note}`;
    else if(c.download) { $('download-xyzv').href=c.download; $('download-xyzv').hidden=false; }
    if(!finite){$('download-xyzv').hidden=true;$('trajectory-download-note').textContent='Preview / analysis CSV uses ideal Lambert coasts joined at planet centers. For Celestia flybys, choose Use in desktop app, load the downloaded file, then choose Integrate & export to construct finite-radius SOI patches and list their extra burns. RoLaMGAS v0.2.4 loads exact candidates; older clients import the search settings.';}
    if(c.community_record){$('download-csv').hidden=false;$('download-csv').href='#analysis-csv';}
    if(!finite){$('download-xyzv').removeAttribute('href');$('download-xyzv').removeAttribute('download');}else $('download-xyzv').setAttribute('download','');
    document.querySelectorAll('.candidate-card').forEach(b => b.setAttribute('aria-pressed', b.dataset.id === c.id));
    canvas.setAttribute('aria-label', `${c.title} heliocentric trajectory in AU. Drag to rotate, scroll to zoom; arrow keys rotate and plus or minus zoom.`);
    $('plot-message').hidden = true;
    updateTime();
  } catch (e) {
    if (token !== requestVersion) return;
    $('plot-message').textContent = e.message;
  } finally {
    if (token === requestVersion) $('mission-view').setAttribute('aria-busy', 'false');
  }
}
function setView(mode) {
  view = mode;
  if (mode === '3d') { yaw = -.35; pitch = .65; }
  if (mode === 'xy') { yaw = 0; pitch = 0; }
  if (mode === 'xz') { yaw = 0; pitch = Math.PI / 2; }
  if (mode === 'yz') { yaw = Math.PI / 2; pitch = Math.PI / 2; }
  document.querySelectorAll('[data-view]').forEach(b => b.setAttribute('aria-pressed', b.dataset.view === mode));
  drawSoon();
}
function rotated(p) {
  const x = p[0] * Math.cos(yaw) - p[1] * Math.sin(yaw), y = p[0] * Math.sin(yaw) + p[1] * Math.cos(yaw);
  return [x, y * Math.cos(pitch) - p[2] * Math.sin(pitch)];
}
function interpolate(path, jd) {
  const n = path.points.length;
  if (n < 2) return path.points[0];
  let k, t;
  if (path.times) {
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (path.times[mid] <= jd) lo = mid; else hi = mid; }
    k = lo; t = (jd - path.times[k]) / Math.max(1e-10, path.times[k+1] - path.times[k]);
  } else {
    const f = Math.max(0, Math.min(1, (jd - path.start) / (path.end - path.start))) * (n - 1);
    k = Math.min(n - 2, Math.floor(f)); t = f - k;
  }
  t = Math.max(0, Math.min(1, t));
  return path.points[k].map((v,i) => v + t * (path.points[k+1][i] - v));
}
function drawSoon() {
  if (!framePending) { framePending = true; requestAnimationFrame(() => { framePending = false; draw(); }); }
}
function draw() {
  const box = canvas.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1), w = box.width, h = box.height;
  if (!w || !h) return;
  if (canvas.width !== Math.round(w*dpr) || canvas.height !== Math.round(h*dpr)) { canvas.width = Math.round(w*dpr); canvas.height = Math.round(h*dpr); }
  ctx.setTransform(dpr,0,0,dpr,0,0); ctx.fillStyle = '#08121e'; ctx.fillRect(0,0,w,h);
  // A fixed background keeps the scientific curve readable while dragging.
  for (let i=0; i<65; i++) { ctx.fillStyle = i%3 ? '#96abc12c' : '#96abc155'; ctx.fillRect((i*179+23)%w, (i*i*37+19)%h, 1, 1); }
  if (!selected) return;
  const context=animatePlanets?selected.planet_paths.filter(p=>bodyVisible(p.body,'markers')||bodyVisible(p.body,'orbits')).flatMap(p=>p.points.map(rotated)):[];
  const all = [[0,0], ...selected.paths.flatMap(p => p.points.map(rotated)),...context];
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const center = [(minX+maxX)/2, (minY+maxY)/2];
  const scale = Math.min((w-110) / Math.max(maxX-minX, .8), (h-100) / Math.max(maxY-minY, .8)) * zoom;
  const project = p => { const r = rotated(p); return [w/2 + (r[0]-center[0])*scale, h/2 - (r[1]-center[1])*scale]; };
  const line = (points, color, width, dash = []) => {
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash); ctx.beginPath();
    points.forEach((p,i) => { const xy = project(p); if (i) ctx.lineTo(...xy); else ctx.moveTo(...xy); }); ctx.stroke(); ctx.setLineDash([]);
  };
  const radius = Math.max(...selected.paths.flatMap(p => p.points.map(p => Math.hypot(...p))), 1) * 1.15;
  const step = radius > 25 ? 10 : radius > 12 ? 5 : radius > 4 ? 2 : radius > 2 ? 1 : .5;
  for (let r=step; r<=radius; r+=step) {
    const ring = Array.from({length:121}, (_,i) => [r*Math.cos(i*Math.PI/60), r*Math.sin(i*Math.PI/60), 0]);
    line(ring, '#28455c65', .65);
  }
  line([[-radius,0,0],[radius,0,0]], '#2e495c55', .6);
  line([[0,-radius,0],[0,radius,0]], '#2e495c55', .6);
  for (const orbit of selected.planet_paths) if(bodyVisible(orbit.body,'orbits')) line(orbit.points, '#64819855', .8, [3,4]);
  selected.paths.forEach((p,i) => line(p.points, colors[i%colors.length], 1.6));
  const dot = (p, color, size) => { const [x,y] = project(p); ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x,y,size,0,Math.PI*2); ctx.fill(); return [x,y]; };
  const sun = dot([0,0,0], '#ffd08a', 4);
  ctx.fillStyle = '#d1b98a'; ctx.font = '10px Segoe UI, sans-serif'; ctx.fillText('Sun', sun[0]+9, sun[1]+4);
  const used = [];
  for (const e of selected.events) {
    if(!bodyVisible(e.body,'markers'))continue;
    const [x,y] = dot(e.position_au, bodyColors[e.body] || '#e7eff6', 3.5);
    let dy = -10;
    while (used.some(p => Math.abs(p[0]-x)<55 && Math.abs(p[1]-(y+dy))<13)) dy += 14;
    used.push([x,y+dy]); ctx.fillStyle = '#c5d6e4'; ctx.font = '10px Segoe UI, sans-serif';
    ctx.fillText(animatePlanets?`${e.body} encounter`:e.body, x+7, y+dy);
  }
  if(animatePlanets&&planetEphemerides){
    for(const body of movingBodyNames(selected)){
      if(!bodyVisible(body,'markers'))continue;
      const position=planetPosition(body,currentJd());if(!position)continue;
      const [x,y]=dot(position,bodyColors[body]||'#e7eff6',5);
      ctx.strokeStyle='#08121e';ctx.lineWidth=1;ctx.beginPath();ctx.arc(x,y,6,0,2*Math.PI);ctx.stroke();
      ctx.fillStyle=bodyColors[body]||'#e7eff6';ctx.fillText(body+' now',x+8,y+15);
    }
  }
  for (const b of selected.burns.filter(globalThis.MissionMetrics.visibleManeuver)) {
    const [x,y] = project(b.position_au); ctx.strokeStyle = '#b7f2ff'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x-3,y-3); ctx.lineTo(x+3,y+3); ctx.moveTo(x+3,y-3); ctx.lineTo(x-3,y+3); ctx.stroke();
  }
  const jd = currentJd(), paths = selected.paths;
  const path = paths.find(p => jd >= p.start && jd <= p.end) || (jd < paths[0].start ? paths[0] : paths.at(-1));
  const spacecraft = interpolate(path, jd), [sx,sy] = project(spacecraft);
  ctx.shadowColor = '#79d8f1'; ctx.shadowBlur = 13; dot(spacecraft, '#fff', 4); ctx.shadowBlur = 0;
  ctx.strokeStyle = '#79d8f199'; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(sx,sy,8,0,Math.PI*2); ctx.stroke();
  // Scale bar has a physical length in AU, in the current projected plane.
  const raw = 65 / scale, pow = 10 ** Math.floor(Math.log10(raw)), nice = [1,2,5,10].find(n => n*pow >= raw) * pow;
  const length = nice * scale;
  ctx.strokeStyle = '#6f8ca3'; ctx.beginPath(); ctx.moveTo(22,h-54); ctx.lineTo(22+length,h-54); ctx.stroke();
  ctx.fillStyle = '#93adc1'; ctx.font = '9px Consolas, monospace'; ctx.fillText(`${Number(nice.toPrecision(3))} AU`,22,h-62);
}

$('destinations').addEventListener('click', e => {
  const b = e.target.closest('[data-target]'); if (!b) return;
  if(destination!==b.dataset.target||smallBodyTarget!=='All')resetDestinationFilters();
  pendingHashTarget=null;destination = b.dataset.target; smallBodyTarget='All'; visibleCount=48; makeDestinations(); renderList();if(selected)updateLocation(selected.id);
});
$('small-body-options').addEventListener('click',e=>{const b=e.target.closest('[data-small-body]');if(!b)return;if(smallBodyTarget!==b.dataset.smallBody)resetDestinationFilters();pendingHashTarget=null;smallBodyTarget=b.dataset.smallBody;visibleCount=48;makeDestinations();renderList();if(selected)updateLocation(selected.id);});
$('candidate-list').addEventListener('click', e => { const b=e.target.closest('[data-id]'); if (b) selectCandidate(b.dataset.id); });
for (const id of ['search','max-c3','max-vinf','max-burns','max-years','launch-year-min','launch-year-max']) $(id).addEventListener('input', ()=>{syncGraphYears();visibleCount=48;renderList();if(selected)updateLocation(selected.id)});
$('sort').addEventListener('change',()=>{visibleCount=48;renderList()});
$('include-yellow').addEventListener('change',()=>{visibleCount=48;renderList()});
$('candidate-more').onclick=()=>{const top=$('candidate-list').scrollTop;visibleCount+=48;renderList();$('candidate-list').scrollTop=top};
$('community-refresh').onclick=()=>syncShared();
for(const suffix of ['min','max'])$('chart-launch-year-'+suffix).addEventListener('input',()=>{$('launch-year-'+suffix).value=$('chart-launch-year-'+suffix).value;$('launch-year-'+suffix).dispatchEvent(new Event('input'))});
$('chart-metric').onchange=()=>{drawTradeoff();if(selected)updateLocation(selected.id)};
function selectPoint(e){const point=e.target.closest('[data-candidate]');if(!point)return;if(e.type==='keydown'&&!['Enter',' '].includes(e.key))return;e.preventDefault();selectCandidate(point.dataset.candidate);$('mission-view').scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'})}
$('tradeoff-svg').addEventListener('click',selectPoint);$('tradeoff-svg').addEventListener('keydown',selectPoint);
function resetDestinationFilters(){for(const id of ['search','max-c3','max-vinf','max-burns','max-years','launch-year-min','launch-year-max'])$(id).value='';$('include-yellow').checked=true;$('sort').value='recommended';visibleCount=48;syncGraphYears();}
$('clear-filters').addEventListener('click',()=>{resetDestinationFilters();renderList();if(selected)updateLocation(selected.id);});
document.querySelector('.projection').addEventListener('click', e => { if (e.target.dataset.view) setView(e.target.dataset.view); });
$('reset-view').addEventListener('click', () => { zoom=1; setView('3d'); });
$('planet-arcs').addEventListener('change', drawSoon);
$('planet-markers').addEventListener('change',drawSoon);
$('body-visibility-options').addEventListener('change',e=>{const t=e.target;if(!t.dataset.previewBody||!previewHidden[t.dataset.previewLayer])return;previewHidden[t.dataset.previewLayer][t.checked?'delete':'add'](t.dataset.previewBody);drawSoon();});
$('play').addEventListener('click', () => { if (!selected) return; if (fraction>=1) fraction=0; setPlaying(!playing); });
$('time').addEventListener('input', () => { setPlaying(false); fraction=Number($('time').value)/1000; updateTime(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) setPlaying(false); });
let drag = null;
canvas.addEventListener('pointerdown', e => { drag=[e.clientX,e.clientY]; canvas.setPointerCapture(e.pointerId); });
canvas.addEventListener('pointermove', e => {
  if (!drag) return;
  yaw+=(e.clientX-drag[0])*.008; pitch=Math.max(-1.55, Math.min(1.55,pitch+(e.clientY-drag[1])*.008)); drag=[e.clientX,e.clientY];
  view='3d'; document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.view==='3d')); drawSoon();
});
for (const event of ['pointerup','pointercancel','lostpointercapture']) canvas.addEventListener(event,()=>drag=null);
canvas.addEventListener('wheel', e => { e.preventDefault(); zoom=Math.max(.25,Math.min(12,zoom*Math.exp(-e.deltaY*.001))); drawSoon(); },{passive:false});
canvas.addEventListener('keydown', e => {
  if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','=','-','0'].includes(e.key)) return;
  e.preventDefault();
  if (e.key==='0') { zoom=1; setView('3d'); return; }
  if (e.key==='ArrowLeft') yaw-=.1; if(e.key==='ArrowRight') yaw+=.1;
  if (e.key==='ArrowUp') pitch=Math.min(1.55,pitch+.1); if(e.key==='ArrowDown') pitch=Math.max(-1.55,pitch-.1);
  if (e.key==='+'||e.key==='=') zoom=Math.min(12,zoom*1.1); if(e.key==='-') zoom=Math.max(.25,zoom/1.1);
  drawSoon();
});
new ResizeObserver(drawSoon).observe(canvas);
for (const name of ['itinerary','model']) {
  $(`tab-${name}`).addEventListener('click', () => {
    for (const other of ['itinerary','model']) { $(other).hidden=other!==name; $(`tab-${other}`).setAttribute('aria-selected',other===name); $(`tab-${other}`).tabIndex=other===name?0:-1; }
  });
  $(`tab-${name}`).addEventListener('keydown', e => { if (['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) { e.preventDefault(); const target=e.key==='Home'?'itinerary':e.key==='End'?'model':name==='model'?'itinerary':'model'; $(`tab-${target}`).click(); $(`tab-${target}`).focus(); } });
}
$('tab-model').tabIndex=-1;
function downloadBlob(blob, filename) {
  const url=URL.createObjectURL(blob), a=document.createElement('a'); a.href=url; a.download=filename; a.hidden=true; document.body.append(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(url),30000);
}
async function exportDesktopCandidate(){
 if(!selected)return;
 try{
  const c=selected;if(c.desktop_record_url&&!c.desktop_record)c.desktop_record=await fetchJson(c.desktop_record_url);
  const document=transferDocument(c,missionName(c)||c.title);
  downloadBlob(new Blob([JSON.stringify(document,null,2)],{type:'application/json'}),`RoLaMGAS-${c.id}.json`);
  $('trajectory-download-note').textContent=document.trajectory?'In the desktop app, choose Import options / website trajectory and select this JSON. The selected dates, branches and burns are loaded and checked without another search. Then choose Integrate & export for a finite-radius Celestia XYZV. Exact-candidate loading is available in RoLaMGAS v0.2.4. Older clients can import its search settings.':'Search options downloaded. This is an integrated concept, so the original CSV/XYZV files remain the authoritative trajectory; these settings start a new Lambert search.';
 }catch(error){$('trajectory-download-note').textContent='Could not prepare desktop transfer: '+error.message;}
}
$('download-json').addEventListener('click',exportDesktopCandidate);
$('save-plot').addEventListener('click',()=>{ if(selected) { draw(); canvas.toBlob(blob=>{if(blob)downloadBlob(blob,`rolamgas-${selected.id}.png`);}); } });

for(const [id,kind] of [['download-csv','csv'],['download-xyzv','xyzv']])$(id).addEventListener('click',e=>{
 if(kind==='xyzv'&&selected&&!finiteRadiusDownload(selected)){e.preventDefault();exportDesktopCandidate();return;}
 if(!selected?.community_record)return;e.preventDefault();
 try{downloadBlob(new Blob([trajectoryText(selected.community_record,kind)],{type:kind==='csv'?'text/csv':'text/plain'}),`rolamgas-${selected.id}.${kind}`)}catch(error){$('trajectory-download-note').textContent='Export failed: '+error.message}
});
function sharedPreview(id){if(!previewCache.has(id))try{previewCache.set(id,thumbnailFor(sharedRecords.get(id)))}catch{previewCache.set(id,'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="220"><rect width="320" height="220" fill="#08121e"/></svg>'))}return previewCache.get(id)}
function addShared(records){let added=0;for(const record of records)try{
 if(sharedRecords.has(record.id))continue;
 const summary=annotateMission(summaryFor(record));summary.historical_match=historicalMatch(record,historicalProfiles);sharedRecords.set(record.id,record);
 const alias=curatedAliases[record.id],key=encounterDayKey(record),existing=encounterDays.get(key);
 if(alias&&catalog.some(c=>c.id===alias)){
  const curated=catalog.find(c=>c.id===alias);carryMissionLabel(summary,curated);
  const previous=curated.received||0;curated.received=Math.max(previous,summary.received||0);
  if(curated.received!==previous)added++;
  encounterDays.set(key,{record,id:alias,curated:true});continue
 }
 if(existing){
  if(existing.curated||!betterDuplicate(record,existing.record)){carryMissionLabel(summary,catalog.find(c=>c.id===existing.id)||summary);displayAliases[record.id]=existing.id;continue}
  const index=catalog.findIndex(c=>c.id===existing.id);if(index>=0){carryMissionLabel(catalog[index],summary);catalog.splice(index,1);}displayAliases[existing.id]=record.id;
 }
 encounterDays.set(key,{record,id:record.id});catalog.push(summary);added++;
}catch{}return added}
function updateCounts(){if(pendingHashTarget&&applyTargetHash(pendingHashTarget))pendingHashTarget=null;$('total-count').textContent=catalog.length.toLocaleString('en-US');$('destination-count').textContent=new Set(catalog.map(c=>c.target)).size;makeDestinations()}
async function syncShared(){
 if(sharedBusy||!sharedEndpoint)return;sharedBusy=true;$('community-refresh').disabled=true;
 try{const result=await fetchUpdates(sharedEndpoint,sharedSince);sharedSince=result.watermark;const added=addShared(result.records);
  if(added){updateCounts();renderList();renderSequenceComparison()}
  $('community-status').textContent=`${catalog.length.toLocaleString('en-US')} interactive trajectories · live shared library connected · checked ${new Date().toLocaleTimeString()}`;
 }catch{$('community-status').textContent='Showing the complete saved archive. Live service unavailable; retrying automatically.'}
 finally{sharedBusy=false;$('community-refresh').disabled=false}
}
try {
 const [data,archive,settings,names,historical,annotations,performance,publications]=await Promise.all([fetchJson('data/index.json?v=20261111b'),fetchJson('data/community_seed_catalog.json?v=20261110b').catch(()=>({candidates:[]})),fetchJson('community_config.json').catch(()=>({})),fetchJson('data/body_names.json?v=20261108b').catch(()=>({})),fetchJson('data/historical_labels.json?v=20261108b').catch(()=>({missions:[]})),fetchJson('data/mission_annotations.json?v=20261111b').catch(()=>({missions:{}})),fetchJson('data/launch_performance_curves.json?v=20261110a').catch(()=>null),fetchJson('data/publication_dates.json?v=20261110b').catch(()=>({candidates:{}}))]);
 registerBodyNames(names);registerBodyCategories(names);historicalProfiles=historical.missions||[];ownerMissions=annotations.missions||{};launchPerformance=performance;publicationHistory=publications.candidates||{};
 catalog.push(...data.cases.filter(c=>c.c3<=250).map(c=>annotateMission(c)));curatedAliases=archive.curated_aliases||{};duplicateAliases=archive.duplicate_aliases||{};sharedSince=archive.received_through||sharedSince;sharedEndpoint=settings.endpoint||'';addShared(archive.candidates);updateCounts();
 $('community-status').textContent=`${catalog.length.toLocaleString('en-US')} interactive trajectories · saved archive loaded`;
 const filters=filterStateFromHash(location.hash),initial=canonicalId(filters.mission||'claudius-uop-2045');
 $('launch-year-min').value=filters.launchMin;$('launch-year-max').value=filters.launchMax;syncGraphYears();const missionFilters=missionFiltersFromHash(location.hash);$('chart-metric').value=missionFilters.metric;for(const [id,key]of [['max-years','maxYears'],['max-c3','maxC3'],['max-vinf','maxVinf'],['max-burns','maxBurns']])$(id).value=missionFilters[key];
 if(filters.target){pendingHashTarget=filters.target;if(applyTargetHash(filters.target))pendingHashTarget=null;makeDestinations()}
 if(filters.mission&&!catalog.some(c=>c.id===initial)&&!sharedRecords.has(initial))await syncShared();
 if(pendingHashTarget&&applyTargetHash(pendingHashTarget)){pendingHashTarget=null;makeDestinations()}
 if(catalog.some(c=>c.id===initial)||sharedRecords.has(initial))await selectCandidate(initial);
 renderList();syncShared();setInterval(()=>{if(!document.hidden)syncShared()},30000);
} catch(e) {
 $('result-count').textContent='Catalog unavailable';$('candidate-list').innerHTML=`<p class="empty">${escapeHtml(e.message)} Reload the page to retry.</p>`;$('mission-view').setAttribute('aria-busy','false');
}
