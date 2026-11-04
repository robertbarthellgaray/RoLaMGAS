import {summaryFor,caseFor,thumbnailFor,trajectoryText,fetchUpdates,bodyName} from './community.js?v=20261104';
import {CATEGORIES,bodyCategory,encounterDayKey,betterDuplicate,rateCandidates,launchYear,sequenceColors,resolveAlias,filterStateFromHash,filterHash} from './library_analysis.js?v=20261104';
const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (n, digits = 2) => Number(n).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits});
const colors = ['#79d8f1', '#ffd08a', '#8ae3bd', '#b4aeff', '#ff9f9a', '#9ed2ff'];
const catalog = [];
const cache = new Map(), sharedRecords = new Map(), previewCache = new Map(), encounterDays=new Map();
let ratings=new Map(), duplicateAliases={}, displayAliases={}, pendingHashTarget=null;
let sharedEndpoint='', sharedSince='1970-01-01T00:00:00.000Z', sharedBusy=false, curatedAliases={}, visibleCount=48;
let destination = 'All', smallBodyTarget = 'All', selected = null, requestVersion = 0, playing = false, lastTick = 0, fraction = 0;
let yaw = -.35, pitch = .65, zoom = 1, view = '3d', framePending = false;
const canvas = $('orbit'), ctx = canvas.getContext('2d');
const bodyColors = {Earth:'#6ea9ff', Venus:'#e3c387', Mercury:'#a7a4a0', Mars:'#e7997e', Jupiter:'#dcc3a6', Saturn:'#f0d28d', Uranus:'#87dfed', Neptune:'#729bff'};

async function fetchJson(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`Could not load saved data (${r.status}). Please retry.`);
  return r.json();
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
function minimumYear(){return $('launch-year-min').value.trim()===''?-Infinity:Number($('launch-year-min').value)}
function maximumYear(){return $('launch-year-max').value.trim()===''?Infinity:Number($('launch-year-max').value)}
function targetRows(){return catalog.filter(c=>targetMatches(c)&&(!CATEGORIES.includes(destination)||smallBodyTarget==='All'||c.target===smallBodyTarget))}
function visibleRows(){
 const search=$('search').value.trim().toLowerCase().replace(/\s+/g,'');
 return targetRows().filter(c=>`${c.title} ${c.sequence} ${c.bodies.join(' ')} ${c.launch_date} ${c.arrival_date}`.toLowerCase().replace(/\s+/g,'').includes(search)
  &&(!c.community||c.classification!=='yellow'||$('include-yellow').checked)&&c.c3<=maximum('max-c3')&&c.vinf<=maximum('max-vinf')&&c.burns_mps<=maximum('max-burns')&&launchYear(c)>=minimumYear()&&launchYear(c)<=maximumYear());
}
function renderList() {
  const rows=visibleRows(),sort=$('sort').value;
  rows.sort((a,b) => sort === 'recommended' ? Number(ratings.get(a.id)?.dominated)-Number(ratings.get(b.id)?.dominated)||Number(b.spotlight) - Number(a.spotlight) || (b.featured_priority || 0) - (a.featured_priority || 0) || (b.received||0)-(a.received||0) : sort==='received'?(b.received||0)-(a.received||0):a[sort]-b[sort]);
  $('result-count').textContent = `${rows.length} ${rows.length === 1 ? 'trajectory' : 'trajectories'}`;
  $('candidate-more').hidden=visibleCount>=rows.length;
  $('candidate-more').textContent=`Show ${Math.min(48,Math.max(0,rows.length-visibleCount))} more (${Math.min(visibleCount,rows.length)} of ${rows.length})`;
  $('candidate-list').innerHTML = rows.length ? rows.slice(0,visibleCount).map(c => `<button type="button" class="candidate-card" data-id="${c.id}" aria-pressed="${c.id === selected?.id}" aria-label="Inspect ${escapeHtml(c.title)}, launch ${c.launch_date}, C3 ${fmt(c.c3)}">
    <div class="card-preview"><img loading="lazy" src="${c.community ? sharedPreview(c.id) : `images/${c.id}.svg`}" width="320" height="220" alt="${escapeHtml(c.sequence)} heliocentric trajectory preview"><span class="card-badge">${c.spotlight ? 'Integrated concept' : escapeHtml(c.model)}</span></div>
    <div class="card-title">${escapeHtml(c.sequence)}<b aria-hidden="true">↗</b></div><p class="card-subtitle">${escapeHtml(c.target)} · ${c.launch_date} → ${c.arrival_date}</p>
    <div class="card-metrics"><div><span>C3 · km²/s²</span>${fmt(c.c3,1)}</div><div><span>Δv · m/s</span>${fmt(c.burns_mps,0)}</div><div><span>FLIGHT · yr</span>${fmt(c.years,1)}</div></div><span class="rating-label ${ratings.get(c.id)?.dominated?'dominated':''}">${escapeHtml(ratings.get(c.id)?.label||'Not compared')}</span></button>`).join('')
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
 const all=targetRows(),years=all.map(launchYear);for(const id of ['launch-year-min','launch-year-max']){$(id).min=Math.min(...years);$(id).max=Math.max(...years)}
 const palette=sequenceColors(all),w=1000,h=340,left=74,right=22,top=22,bottom=56,maxX=Math.max(1,...rows.map(c=>c.c3))*1.06,maxY=Math.max(.1,...rows.map(c=>c.years))*1.08;
 let svg='';
 for(let i=0;i<=5;i++){const x=left+(w-left-right)*i/5,y=h-bottom-(h-top-bottom)*i/5;svg+=`<path d="M${x},${top}V${h-bottom}M${left},${y}H${w-right}" stroke="#26394a" stroke-width="1"/><text x="${x}" y="${h-bottom+22}" text-anchor="middle">${fmt(maxX*i/5,1)}</text><text x="${left-10}" y="${y+4}" text-anchor="end">${fmt(maxY*i/5,1)}</text>`}
 svg+=`<text class="axis-label" x="${(left+w-right)/2}" y="${h-5}" text-anchor="middle">Launch C3 (km²/s²)</text><text class="axis-label" transform="translate(17 ${(top+h-bottom)/2}) rotate(-90)" text-anchor="middle">Flight time (years)</text>`;
 svg+=rows.map(c=>`<circle class="tradeoff-point" data-candidate="${escapeHtml(c.id)}" tabindex="0" role="button" aria-pressed="${c.id===selected?.id}" aria-label="${escapeHtml(c.sequence)}, launch ${c.launch_date}, C3 ${fmt(c.c3)}, ${fmt(c.years)} years; open trajectory and downloads" cx="${left+c.c3/maxX*(w-left-right)}" cy="${h-bottom-c.years/maxY*(h-top-bottom)}" r="5" fill="${palette.get(c.sequence)}"><title>${escapeHtml(c.sequence)} · launch ${c.launch_date} · C3 ${fmt(c.c3)} km²/s² · ${fmt(c.years,3)} years · ${escapeHtml(ratings.get(c.id)?.label||'')}</title></circle>`).join('');
 $('tradeoff-svg').innerHTML=svg;
 $('tradeoff-legend').innerHTML=[...palette].filter(([sequence])=>rows.some(c=>c.sequence===sequence)).map(([sequence,color])=>`<span><i class="sequence-swatch" style="background:${color}"></i>${escapeHtml(sequence)}</span>`).join('');
 $('tradeoff-status').textContent=`${target} · ${rows.length} trajectories · ${Math.min(...rows.map(launchYear))}–${Math.max(...rows.map(launchYear))} launches. Select a dot to inspect and download.`;
}
function showRating(id){
 const r=ratings.get(id),element=$('candidate-rating');
 element.textContent=r?(r.dominated?`${r.count} saved alternative${r.count===1?'':'s'} offer equal or better costs for this target within two years of launch.`:`${r.label} among saved alternatives for this target within two years of launch. This is a cost comparison.`):'';
 if(r?.alternative){const b=document.createElement('button');b.type='button';b.className='subtle-button';b.textContent='Inspect a better alternative →';b.onclick=()=>selectCandidate(r.alternative);element.append(b)}
}
function canonicalId(id){return resolveAlias(id,{...duplicateAliases,...curatedAliases,...displayAliases})}
function updateLocation(id){const hash=filterHash({target:selectedTarget()||destination,mission:id,launchMin:$('launch-year-min').value,launchMax:$('launch-year-max').value});history.replaceState(null,'',`${location.pathname}${location.search}${hash}`)}
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
    if (!c) { c = sharedRecords.has(id) ? caseFor(sharedRecords.get(id)) : await fetchJson(`data/cases/${encodeURIComponent(id)}.json`); cache.set(id, c); }
    if (token !== requestVersion) return;
    selected = c; fraction = 0; zoom = 1; setView('3d');
    updateLocation(c.id);showRating(c.id);
    document.querySelectorAll('[data-candidate]').forEach(p=>p.setAttribute('aria-pressed',p.dataset.candidate===c.id));
    $('model-label').textContent = c.model.toUpperCase();
    $('mission-title').textContent = c.title;
    $('mission-dates').textContent = `${c.launch_date} → ${c.arrival_date} (TDB) · ${fmt(c.years,3)} years / ${fmt(c.end-c.start,1)} days · ${c.bodies.join(' → ')}`;
    $('mission-id').textContent = c.id;
    const metrics = [ ['Launch C3', fmt(c.c3), 'km²/s²'], ['Cruise Δv', fmt(c.burns_mps,1), 'm/s'], ['Arrival V∞', fmt(c.vinf), 'km/s'], ['Flight time', fmt(c.years), 'years'] ];
    $('metrics').innerHTML = metrics.map(([label,value,unit]) => `<div class="metric"><p>${label}</p><strong>${value}</strong><small>${unit}</small></div>`).join('');
    const events = [...c.events.map(e => ({...e, burn:false})), ...c.burns.map(b => ({...b, burn:true}))].sort((a,b) => a.jd - b.jd);
    $('events').innerHTML = events.map(e => {
      const f = c.flybys.find(f => Math.abs(f.jd - e.jd) < .0001);
      let detail = e.burn ? `${fmt(e.magnitude_mps,2)} m/s` : e.kind;
      if (e.altitude_km != null) detail += ` · ${fmt(e.altitude_km,0)} km altitude`;
      if (f) detail = `${fmt(f.altitude_km,0)} km inferred altitude · ${fmt(f.mismatch_mps,3)} m/s |ΔV∞|${f.powered_mps ? ` · ${fmt(f.powered_mps,1)} m/s powered` : ''}`;
      return `<tr><td><i class="event-dot ${e.burn?'burn-dot':''}"></i>${escapeHtml(e.burn ? e.kind : e.body)}</td><td>${escapeHtml(e.date.replace('T',' ').replace(/\.[0-9]+(?= TDB)/,'').replace(' TDB',''))}</td><td>${e.jd.toFixed(6)}</td><td>${escapeHtml(detail)}</td></tr>`;
    }).join('');
    $('model-note').textContent = c.note;
    const labels = {source:'Data source', coordinates:'Coordinates', time_scale:'Time scale', plot_units:'Preview units', candidate_id:'Candidate', speed_tolerance_mps:'Saved speed tolerance (m/s)', sha256:'XYZV SHA-256', export_units:'Export columns', ephemerides:'Ephemerides', planet_arcs:'Planet context',target_horizons_id:'Horizons target ID',target_ephemeris:'Target representation'};
    $('provenance').innerHTML = Object.entries(labels).filter(([key]) => c.provenance[key] != null).map(([key,label]) => `<dt>${label}</dt><dd>${escapeHtml(c.provenance[key])}</dd>`).join('');
    if(c.validation) {
      const v=c.validation;
      $('provenance').innerHTML += `<dt>Gallery admission</dt><dd>${v.passed?'Passed independent vector and coast checks':'Not admitted'}</dd><dt>Worst |ΔV∞|</dt><dd>${fmt(v.max_vinf_mismatch_mps,6)} m/s (limit 1 m/s)</dd><dt>Largest DSM</dt><dd>${fmt(v.max_single_dsm_mps,3)} m/s (limit 700 m/s)</dd><dt>Coast endpoint error</dt><dd>${fmt(v.max_coast_endpoint_error_km*1000,3)} m maximum</dd>`;
    }
    if(c.integration_validation) {
      $('provenance').innerHTML += `<dt>JPL clearance audit</dt><dd>Passed · Sun and eight planetary surfaces</dd><dt>Audit scope</dt><dd>${escapeHtml(c.integration_validation.scope)}</dd>`;
    }
    $('planet-arcs').disabled=Boolean(c.community);
    $('planet-arcs').title=c.community?'This shared record contains encounter markers, without full planet ephemeris arcs.':'';
    const files = c.trajectory_files;
    for (const [name,key] of [['download-csv','csv'],['download-xyzv','xyzv'],['download-state-readme','readme']]) {
      const link=$(name); link.hidden=!files?.[key];
      if(files?.[key]) link.href=files[key];
    }
    if(files) $('trajectory-download-note').textContent=`${files.rows.toLocaleString()} saved position/velocity states · ${files.units} · ${files.coordinates}. ${files.note}`;
    else if(c.download) { $('download-xyzv').href=c.download; $('download-xyzv').hidden=false; }
    if(c.community_record){for(const id of ['download-csv','download-xyzv']){$(id).hidden=false;$(id).href='#export'}$('trajectory-download-note').textContent='Downloads sample the saved Sun-only Lambert coasts (JD TDB, km, km/s). Planet-center joins are not finite-radius flybys; use the desktop exporter for flyby rendering and validation.';}
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
  const all = [[0,0], ...selected.paths.flatMap(p => p.points.map(rotated))];
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
  if ($('planet-arcs').checked) for (const orbit of selected.planet_paths) line(orbit.points, '#64819855', .8, [3,4]);
  selected.paths.forEach((p,i) => line(p.points, colors[i%colors.length], 1.6));
  const dot = (p, color, size) => { const [x,y] = project(p); ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x,y,size,0,Math.PI*2); ctx.fill(); return [x,y]; };
  const sun = dot([0,0,0], '#ffd08a', 4);
  ctx.fillStyle = '#d1b98a'; ctx.font = '10px Segoe UI, sans-serif'; ctx.fillText('Sun', sun[0]+9, sun[1]+4);
  const used = [];
  for (const e of selected.events) {
    const [x,y] = dot(e.position_au, bodyColors[e.body] || '#e7eff6', 3.5);
    let dy = -10;
    while (used.some(p => Math.abs(p[0]-x)<55 && Math.abs(p[1]-(y+dy))<13)) dy += 14;
    used.push([x,y+dy]); ctx.fillStyle = '#c5d6e4'; ctx.font = '10px Segoe UI, sans-serif';
    ctx.fillText(e.body, x+7, y+dy);
  }
  for (const b of selected.burns) {
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
  pendingHashTarget=null;destination = b.dataset.target; smallBodyTarget='All'; visibleCount=48; makeDestinations(); renderList();if(selected)updateLocation(selected.id);
});
$('small-body-options').addEventListener('click',e=>{const b=e.target.closest('[data-small-body]');if(!b)return;pendingHashTarget=null;smallBodyTarget=b.dataset.smallBody;visibleCount=48;makeDestinations();renderList();if(selected)updateLocation(selected.id);});
$('candidate-list').addEventListener('click', e => { const b=e.target.closest('[data-id]'); if (b) selectCandidate(b.dataset.id); });
for (const id of ['search','max-c3','max-vinf','max-burns','launch-year-min','launch-year-max']) $(id).addEventListener('input', ()=>{visibleCount=48;renderList();if(selected)updateLocation(selected.id)});
$('sort').addEventListener('change',()=>{visibleCount=48;renderList()});
$('include-yellow').addEventListener('change',()=>{visibleCount=48;renderList()});
$('candidate-more').onclick=()=>{const top=$('candidate-list').scrollTop;visibleCount+=48;renderList();$('candidate-list').scrollTop=top};
$('community-refresh').onclick=()=>syncShared();
$('reset-years').onclick=()=>{$('launch-year-min').value='';$('launch-year-max').value='';visibleCount=48;renderList();if(selected)updateLocation(selected.id)};
function selectPoint(e){const point=e.target.closest('[data-candidate]');if(!point)return;if(e.type==='keydown'&&!['Enter',' '].includes(e.key))return;e.preventDefault();selectCandidate(point.dataset.candidate);$('mission-view').scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'})}
$('tradeoff-svg').addEventListener('click',selectPoint);$('tradeoff-svg').addEventListener('keydown',selectPoint);
$('clear-filters').addEventListener('click', () => { ['search','max-c3','max-vinf','max-burns'].forEach(id => $(id).value=''); renderList(); });
document.querySelector('.projection').addEventListener('click', e => { if (e.target.dataset.view) setView(e.target.dataset.view); });
$('reset-view').addEventListener('click', () => { zoom=1; setView('3d'); });
$('planet-arcs').addEventListener('change', drawSoon);
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
$('download-json').addEventListener('click',()=>{ if(selected) downloadBlob(new Blob([JSON.stringify(selected.community_record||selected,null,2)],{type:'application/json'}),`rolamgas-${selected.id}.json`); });
$('save-plot').addEventListener('click',()=>{ if(selected) { draw(); canvas.toBlob(blob=>{if(blob)downloadBlob(blob,`rolamgas-${selected.id}.png`);}); } });

for(const [id,kind] of [['download-csv','csv'],['download-xyzv','xyzv']])$(id).addEventListener('click',e=>{
 if(!selected?.community_record)return;e.preventDefault();
 try{downloadBlob(new Blob([trajectoryText(selected.community_record,kind)],{type:kind==='csv'?'text/csv':'text/plain'}),`rolamgas-${selected.id}.${kind}`)}catch(error){$('trajectory-download-note').textContent='Export failed: '+error.message}
});
function sharedPreview(id){if(!previewCache.has(id))try{previewCache.set(id,thumbnailFor(sharedRecords.get(id)))}catch{previewCache.set(id,'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="220"><rect width="320" height="220" fill="#08121e"/></svg>'))}return previewCache.get(id)}
function addShared(records){let added=0;for(const record of records)try{
 if(sharedRecords.has(record.id))continue;
 const summary=summaryFor(record);sharedRecords.set(record.id,record);
 const alias=curatedAliases[record.id],key=encounterDayKey(record),existing=encounterDays.get(key);
 if(alias&&catalog.some(c=>c.id===alias)){encounterDays.set(key,{record,id:alias,curated:true});continue}
 if(existing){
  if(existing.curated||!betterDuplicate(record,existing.record)){displayAliases[record.id]=existing.id;continue}
  const index=catalog.findIndex(c=>c.id===existing.id);if(index>=0)catalog.splice(index,1);displayAliases[existing.id]=record.id;
 }
 encounterDays.set(key,{record,id:record.id});catalog.push(summary);added++;
}catch{}return added}
function updateCounts(){if(pendingHashTarget&&applyTargetHash(pendingHashTarget))pendingHashTarget=null;ratings=rateCandidates(catalog);$('total-count').textContent=catalog.length.toLocaleString('en-US');$('destination-count').textContent=new Set(catalog.map(c=>c.target)).size;makeDestinations();if(selected)showRating(selected.id)}
async function syncShared(){
 if(sharedBusy||!sharedEndpoint)return;sharedBusy=true;$('community-refresh').disabled=true;
 try{const result=await fetchUpdates(sharedEndpoint,sharedSince);sharedSince=result.watermark;const added=addShared(result.records);
  if(added){updateCounts();renderList()}
  $('community-status').textContent=`${catalog.length.toLocaleString('en-US')} interactive trajectories · live shared library connected · checked ${new Date().toLocaleTimeString()}`;
 }catch{$('community-status').textContent='Showing the complete saved archive. Live service unavailable; retrying automatically.'}
 finally{sharedBusy=false;$('community-refresh').disabled=false}
}
try {
 const [data,archive,settings]=await Promise.all([fetchJson('data/index.json'),fetchJson('data/community_seed_catalog.json?v=20261104').catch(()=>({candidates:[]})),fetchJson('community_config.json').catch(()=>({}))]);
 catalog.push(...data.cases.filter(c=>c.c3<=250));curatedAliases=archive.curated_aliases||{};duplicateAliases=archive.duplicate_aliases||{};sharedSince=archive.received_through||sharedSince;sharedEndpoint=settings.endpoint||'';addShared(archive.candidates);updateCounts();
 $('community-status').textContent=`${catalog.length.toLocaleString('en-US')} interactive trajectories · saved archive loaded`;
 const filters=filterStateFromHash(location.hash),initial=canonicalId(filters.mission||'claudius-uop-2045');
 $('launch-year-min').value=filters.launchMin;$('launch-year-max').value=filters.launchMax;
 if(filters.target){pendingHashTarget=filters.target;if(applyTargetHash(filters.target))pendingHashTarget=null;makeDestinations()}
 if(filters.mission&&!catalog.some(c=>c.id===initial)&&!sharedRecords.has(initial))await syncShared();
 if(pendingHashTarget&&applyTargetHash(pendingHashTarget)){pendingHashTarget=null;makeDestinations()}
 if(catalog.some(c=>c.id===initial)||sharedRecords.has(initial))await selectCandidate(initial);
 renderList();syncShared();setInterval(()=>{if(!document.hidden)syncShared()},30000);
} catch(e) {
 $('result-count').textContent='Catalog unavailable';$('candidate-list').innerHTML=`<p class="empty">${escapeHtml(e.message)} Reload the page to retry.</p>`;$('mission-view').setAttribute('aria-busy','false');
}
