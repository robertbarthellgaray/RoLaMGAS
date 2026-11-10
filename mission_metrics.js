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
  function launchCapacities(document,c3) {
    if(!document?.vehicles||!Number.isFinite(c3)||c3<0)return [];
    const grid=(document.queries||[]).map(q=>q.c3);
    return document.vehicles.filter(visibleLaunchVehicle).map(vehicle=>{
      const points=vehicle.points||[],exact=points.find(p=>Math.abs(p[0]-c3)<1e-9);
      if(exact)return {...vehicle,capacity_kg:exact[1],interpolated:false};
      const lower=points.filter(p=>p[0]<c3).at(-1),upper=points.find(p=>p[0]>c3);
      if(!lower||!upper||grid.some(v=>lower[0]<v&&v<upper[0]))return {...vehicle,capacity_kg:null,interpolated:false};
      return {...vehicle,capacity_kg:lower[1]+(upper[1]-lower[1])*(c3-lower[0])/(upper[0]-lower[0]),interpolated:true,bracket_c3:[lower[0],upper[0]]};
    });
  }
  root.MissionMetrics=Object.freeze({bodies,parkingInjection,summary,normalized,compare,ephemerisPosition,visibleManeuver,visibleLaunchVehicle,launchCapacities});
})(globalThis);
