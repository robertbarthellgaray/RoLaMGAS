// Shared, offline display calculations. Does not alter trajectory dynamics or budgets.
(function (root) {
  'use strict';
  const bodies = Object.freeze({
    Mercury:[22031.86855,2439.7], Venus:[324858.592,6051.8], Earth:[398600.435436,6378.137],
    Mars:[42828.375816,3396.19], Jupiter:[126686531.9,71492], Saturn:[37931206.234,60268],
    Uranus:[5793950.6103,25559], Neptune:[6835099.5,24764]
  });
  function parkingInjection(c3, altitudeKm, body='Earth') {
    if (!Number.isFinite(c3)||c3<0||!Number.isFinite(altitudeKm)||altitudeKm<=0||!bodies[body]) return null;
    const [mu,radius]=bodies[body], r=radius+altitudeKm;
    const circular=Math.sqrt(mu/r), hyperbolic=Math.sqrt(c3+2*mu/r);
    return {body,altitudeKm,radiusKm:r,circularKms:circular,hyperbolicKms:hyperbolic,deltaVKms:hyperbolic-circular};
  }
  function summary(values, selected) {
    const sorted=values.filter(Number.isFinite).slice().sort((a,b)=>a-b),n=sorted.length;
    if(!n)return null;
    const mean=sorted.reduce((s,x)=>s+x,0)/n, median=n%2?sorted[(n-1)/2]:(sorted[n/2-1]+sorted[n/2])/2;
    const stddev=Math.sqrt(sorted.reduce((s,x)=>s+(x-mean)**2,0)/n);
    const below=sorted.filter(x=>x<selected).length,equal=sorted.filter(x=>x===selected).length;
    return {n,mean,median,stddev,min:sorted[0],max:sorted.at(-1),percentile:Number.isFinite(selected)?100*(below+equal/2)/n:null};
  }
  function normalized(row) {
    return {sequence:row.sequence,target:String(row.target??row.bodies?.at(-1)??row.target_id??row.body_ids?.at(-1)??''),
      c3:row.c3??row.launch_c3_km2_s2,years:row.years??row.duration_years??(row.dates_jd_tdb?.length>1?(row.dates_jd_tdb.at(-1)-row.dates_jd_tdb[0])/365.25:NaN),vinf:row.vinf??row.arrival_vinf_kms};
  }
  function compare(rows,selected) {
    const choice=normalized(selected),peers=rows.map(normalized).filter(r=>r.target===choice.target&&r.sequence===choice.sequence);
    return {n:peers.length,c3:summary(peers.map(r=>r.c3),choice.c3),years:summary(peers.map(r=>r.years),choice.years),vinf:summary(peers.map(r=>r.vinf),choice.vinf)};
  }
  // Cubic Hermite interpolation, with velocities in coordinate units per day.
  // No extrapolation: missing coverage must be shown explicitly by the viewer.
  function ephemerisPosition(table,jd) {
    const rows=table?.states;
    if(!rows?.length||!Number.isFinite(jd)||jd<rows[0][0]||jd>rows.at(-1)[0])return null;
    let lo=0,hi=rows.length-1;
    while(hi-lo>1){const m=(lo+hi)>>1;if(rows[m][0]<=jd)lo=m;else hi=m;}
    const a=rows[lo],b=rows[hi],dt=b[0]-a[0];if(dt<=0)return a.slice(1,4);
    const t=(jd-a[0])/dt,h00=2*t**3-3*t**2+1,h10=t**3-2*t**2+t,h01=-2*t**3+3*t**2,h11=t**3-t**2;
    return [0,1,2].map(i=>h00*a[1+i]+h10*dt*a[4+i]+h01*b[1+i]+h11*dt*b[4+i]);
  }
  function visibleManeuver(burn) {
    const kind=String(burn.kind||burn.label||'');
    const mps=burn.magnitude_mps??(burn.magnitude_kms==null?NaN:burn.magnitude_kms*1000);
    return !(/(?:coast.*targeting correction|targeting correction.*coast)/i.test(kind)&&Number.isFinite(mps)&&mps>=0&&mps<.005);
  }
  function visibleLaunchVehicle(vehicle) {
    const name=String(vehicle?.vehicle||'').trim();
    return !/^Vulcan\s*\(VC0\)$/i.test(name)&&!/^Falcon 9\s*\(Full Thrust,\s*RTLS\s*\)$/i.test(name);
  }
  function launchCapacities(document,c3,exactResponse=null) {
    if(!document?.vehicles||!Number.isFinite(c3)||c3<0)return [];
    const defaultGrid=(document.queries||[]).map(q=>q.c3);
    const rows=document.vehicles.filter(visibleLaunchVehicle).filter(v=>!v.kickstage_id||c3>=100).map(vehicle=>{
      const grid=vehicle.query_grid_c3||defaultGrid;
      const points=vehicle.points||[],exact=points.find(p=>Math.abs(p[0]-c3)<1e-9);
      if(exact)return {...vehicle,capacity_kg:exact[1],interpolated:false,sample_c3:exact[0]};
      const lower=points.filter(p=>p[0]<c3).at(-1),upper=points.find(p=>p[0]>c3);
      if(!lower||!upper||grid.some(v=>lower[0]<v&&v<upper[0])){
        const model=vehicle.extrapolation,range=model?.c3_range;
        if(model&&range&&range[0]<=c3&&c3<=range[1]){
          const speed=Math.sqrt(2*398600.4418/6578.137+c3);let value=NaN;
          if(model.kind==='effective_exponential')value=model.amplitude_kg*Math.exp(-(speed-model.reference_speed_km_s)/model.effective_exhaust_speed_km_s)-model.effective_inert_mass_kg;
          else if(model.kind==='effective_stage'){
            const denominator=Math.expm1((speed-model.velocity_offset_km_s)/model.effective_exhaust_speed_km_s);
            if(denominator>0)value=model.propellant_kg/denominator-model.effective_inert_mass_kg;
          }
          if(Number.isFinite(value))return {...vehicle,capacity_kg:Math.max(0,value),interpolated:false,extrapolated:true,display_rounding_kg:100};
        }
        return {...vehicle,capacity_kg:null,interpolated:false};
      }
      return {...vehicle,capacity_kg:lower[1]+(upper[1]-lower[1])*(c3-lower[0])/(upper[0]-lower[0]),interpolated:true,bracket_c3:[lower[0],upper[0]]};
    });
    const exact=(exactResponse?.vehicles||[]).filter(visibleLaunchVehicle);
    const names=new Set(exact.map(r=>r.vehicle));
    return [...exact,...rows.filter(r=>!names.has(r.vehicle))];
  }
  function launchCapacitySource(row) {
    let text=row.source_label||'NASA LSP / NLS-II';
    if(row.extrapolated)text='Extrapolated estimate · '+text;
    if(row.capacity_kg!=null&&row.confidence95_points){
      const at=row.interpolated?row.bracket_c3:[row.sample_c3];
      const intervals=row.confidence95_points.filter(p=>at?.some(c3=>Math.abs(p[0]-c3)<1e-9));
      if(intervals.length)text+=' · source 95% model interval'+(row.interpolated?'s at bracket samples':'')+': '+intervals.map(p=>'C3 '+p[0]+' → '+p[1]+'–'+p[2]+' kg').join('; ');
    }
    return text;
  }
  function launchCapacityValue(row) {
    if(!Number.isFinite(row.capacity_kg))return 'Not tabulated';
    const step=row.display_rounding_kg||1,mass=Math.round(row.capacity_kg/step)*step;
    if(row.capacity_kg>0&&mass===0)return '<'+step.toLocaleString('en-US')+' (estimate)';
    if(row.capacity_kg===0&&(row.extrapolated||row.data_kind==='modeled_kickstage_combination'))return '0 (model)';
    return (row.interpolated||row.extrapolated||row.data_kind?'≈ ':'')+mass.toLocaleString('en-US',{maximumFractionDigits:0});
  }
  function launchCapacityCoverage(row) {
    const points=row.points||[],number=x=>x.toLocaleString('en-US',{maximumFractionDigits:3});
    if(row.extrapolated)return 'Model C3 '+row.extrapolation.c3_range.map(number).join('–')+'; outside source coverage';
    if(row.data_kind==='modeled_kickstage_combination')return 'Concept model C3 100–200';
    if(points.length===1)return 'Reference only: '+number(points[0][1])+' kg at C3 '+number(points[0][0]);
    if(points.length>1)return 'C3 '+number(points[0][0])+'–'+number(points.at(-1)[0])+'; sampled coverage';
    return 'Exact NASA query; configuration-specific';
  }
  const chartMetrics=Object.freeze({
    years:{label:'Flight time (Julian years)'}, c3:{label:'Launch C3 (km²/s²)'},
    vinf:{label:'Arrival V∞ (km/s)'}, burns:{label:'Modeled cruise Δv (m/s)'},
    departure:{label:'Departure date (TDB)',date:true}, arrival:{label:'Arrival date (TDB)',date:true}
  });
  function chartEpoch(row,last=false) {
    const dates=row.dates_jd_tdb;
    const jd=Array.isArray(dates)&&dates.length>1?dates[last?dates.length-1:0]:row[last?'end':'start'];
    if(Number.isFinite(jd))return jd;
    const text=row[last?'arrival_date':'launch_date'];
    if(typeof text!=='string')return NaN;
    // These are calendar labels in TDB. UTC APIs only perform calendar arithmetic;
    // no UTC/TDB conversion is implied or needed for the display coordinates.
    const iso=text.trim().replace(/\s*TDB$/,'').replace(' ','T');
    if(!/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$/.test(iso))return NaN;
    return Date.parse(iso+(iso.includes('T')?'Z':'T00:00:00Z'))/86400000+2440587.5;
  }
  function chartValue(row,key) {
    if(key==='departure'||key==='arrival')return chartEpoch(row,key==='arrival');
    if(key==='years'){
      const start=chartEpoch(row),end=chartEpoch(row,true);
      return Number.isFinite(start)&&Number.isFinite(end)?(end-start)/365.25:(row.years??row.duration_years);
    }
    if(key==='c3')return row.c3??row.launch_c3_km2_s2;
    if(key==='vinf')return row.vinf??row.arrival_vinf_kms;
    if(key==='burns')return row.burns_mps??(Number.isFinite(row.total_dsm_kms)?1000*row.total_dsm_kms:NaN);
    return NaN;
  }
  function chartOptions(options={}) {
    return {x:Object.hasOwn(chartMetrics,options.x)?options.x:'years',y:Object.hasOwn(chartMetrics,options.y)?options.y:'c3',
      color:options.color==='sequence'||Object.hasOwn(chartMetrics,options.color)?options.color:'sequence'};
  }
  function chartDomain(values,key) {
    let lo=Infinity,hi=-Infinity;
    for(const v of values)if(Number.isFinite(v)){lo=Math.min(lo,v);hi=Math.max(hi,v);}
    if(lo===Infinity)return [0,1];
    if(chartMetrics[key]?.date){const pad=Math.max((hi-lo)*.04,1/24);return [lo-pad,hi+pad];}
    return [0,Math.max(.1,hi)*1.08];
  }
  function chartTick(value,key,span=1) {
    if(!Number.isFinite(value))return '—';
    if(chartMetrics[key]?.date){
      const time=(value-2440587.5)*86400000;
      if(!Number.isFinite(time)||Math.abs(time)>8.64e15)return '—';
      const iso=new Date(time).toISOString();
      return span<3?iso.slice(5,10)+' '+iso.slice(11,16):iso.slice(0,10);
    }
    return value.toFixed(span<1?2:1);
  }
  function chartColor(value,domain) {
    const stops=[[68,1,84],[59,82,139],[33,145,140],[94,201,98],[253,231,37]];
    const t=domain[1]===domain[0] ? 0.5 : Math.max(0,Math.min(1,(value-domain[0])/(domain[1]-domain[0])));
    const u=t*(stops.length-1),i=Math.min(stops.length-2,Math.floor(u)),f=u-i;
    return 'rgb('+stops[i].map((v,k)=>Math.round(v+(stops[i+1][k]-v)*f)).join(',')+')';
  }
  function chartModel(rows,options={},palette=new Map()) {
    const opts=chartOptions(options),valid=(v,key)=>Number.isFinite(v)&&(chartMetrics[key].date||v>=0);
    const points=[];
    for(const row of rows){const x=chartValue(row,opts.x),y=chartValue(row,opts.y),color=opts.color==='sequence'?null:chartValue(row,opts.color);
      if(valid(x,opts.x)&&valid(y,opts.y)&&(opts.color==='sequence'||valid(color,opts.color)))points.push({row,x,y,color});
    }
    const xDomain=chartDomain(points.map(p=>p.x),opts.x),yDomain=chartDomain(points.map(p=>p.y),opts.y);
    let colorLo=Infinity,colorHi=-Infinity;for(const p of points)if(p.color!==null){colorLo=Math.min(colorLo,p.color);colorHi=Math.max(colorHi,p.color);}
    const colorDomain=colorLo===Infinity?[0,1]:[colorLo,colorHi];
    for(const p of points)p.fill=opts.color==='sequence'?(palette.get(p.row.sequence)||'#79d8f1'):chartColor(p.color,colorDomain);
    return {...opts,points,xDomain,yDomain,colorDomain,skipped:rows.length-points.length,
      sampledDates:opts.x==='departure'&&opts.y==='arrival'};
  }
  function chartGrid(model,{w=1000,h=340,left=108,right=36,top=22,bottom=65}={}) {
    const label=(axis,v)=>chartTick(v,model[axis],model[axis+'Domain'][1]-model[axis+'Domain'][0]);
    let html='';
    for(let i=0;i<=5;i++){
      const x=left+(w-left-right)*i/5,y=h-bottom-(h-top-bottom)*i/5;
      html+=`<path d="M${x},${top}V${h-bottom}M${left},${y}H${w-right}" stroke="#2c4056"/><text x="${x}" y="${h-bottom+22}" text-anchor="middle">${label('x',model.xDomain[0]+(model.xDomain[1]-model.xDomain[0])*i/5)}</text><text x="${left-10}" y="${y+4}" text-anchor="end">${label('y',model.yDomain[0]+(model.yDomain[1]-model.yDomain[0])*i/5)}</text>`;
    }
    return html+`<text class="axis-label" x="${(left+w-right)/2}" y="${h-6}" text-anchor="middle">${chartMetrics[model.x].label}</text><text class="axis-label" transform="translate(18 ${(top+h-bottom)/2}) rotate(-90)" text-anchor="middle">${chartMetrics[model.y].label}</text>`;
  }
  function chartPosition(value,domain){return (value-domain[0])/(domain[1]-domain[0]);}
  function chartColorLegend(model) {
    if(model.color==='sequence'||!model.points.length)return '';
    const range=model.colorDomain,span=range[1]-range[0];
    return `<span class="chart-color-title">Color: ${chartMetrics[model.color].label}</span><span class="chart-color-scale"><span>${chartTick(range[0],model.color,span)}</span><i class="chart-color-ramp" aria-hidden="true"></i><span>${chartTick(range[1],model.color,span)}</span></span>`;
  }
  root.MissionMetrics=Object.freeze({bodies,parkingInjection,summary,normalized,compare,ephemerisPosition,visibleManeuver,visibleLaunchVehicle,launchCapacities,launchCapacitySource,launchCapacityValue,launchCapacityCoverage,
    chartMetrics,chartEpoch,chartValue,chartOptions,chartDomain,chartTick,chartColor,chartModel,chartGrid,chartPosition,chartColorLegend});
})(globalThis);
