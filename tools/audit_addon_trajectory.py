"""Read-only audit of a Sun-centered Celestia addon ZIP; save plots and conic diagnostics."""
from pathlib import Path
import argparse,io,json,re,sys,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap,numpy as np
from ephemeris import AU,DAY,MU_SUN,calendar,atomic_json
from dynamics import kepler
from integrate_export import heliocentric_orbit_summary

def audit(archive,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        trajectories=[n for n in z.namelist() if n.endswith('.xyzv')]
        if len(trajectories)!=1:raise ValueError('Expected one XYZV in this addon ZIP')
        entry=z.getinfo(trajectories[0])
        if entry.file_size>100*1024*1024:raise ValueError('XYZV is too large for this audit')
        data=np.loadtxt(io.BytesIO(z.read(entry)))
        reports=[n for n in z.namelist() if n.endswith('integration_report.json')]
        if len(reports)!=1:raise ValueError('Expected one integration report')
        report=json.loads(z.read(reports[0]));manifests=[n for n in z.namelist() if n.endswith('package_manifest.json')]
        manifest=json.loads(z.read(manifests[0])) if len(manifests)==1 else {}
        sscs=[z.read(n).decode('utf-8-sig') for n in z.namelist() if n.endswith('.ssc')]
        if not any(re.search(r'Center\s+"Sol"',s) for s in sscs):raise ValueError('This audit requires a Sun-centered addon')
    if data.ndim!=2 or data.shape[1]!=7 or not np.isfinite(data).all() or not np.all(np.diff(data[:,0])>0):raise ValueError('Invalid XYZV columns or dates')
    epoch=report['final_encounter_jd_tdb'];post=data[data[:,0]>=epoch-1e-8]
    if len(post)<2:raise ValueError('No post-encounter samples in this ZIP')
    initial=post[0,1:];orbit=heliocentric_orbit_summary(initial,post[0,0])
    radii=np.linalg.norm(post[:,1:4],axis=1);energy=np.sum(post[:,4:]**2,axis=1)/2-MU_SUN/radii
    radial=np.sum(post[:,1:4]*post[:,4:],axis=1)/radii
    # This comparison applies only to an already Sun-only continuation.
    forces=[f for f in report.get('force_segments',[]) if f.get('start_jd_tdb',-1)>=epoch-1e-8]
    solar_only=bool(forces) and all(f['center']=='Sun' for f in forces)
    endpoint_error=None
    if solar_only:
        expected,_=kepler(initial[:3],initial[3:],(post[-1,0]-post[0,0])*DAY)
        endpoint_error=float(np.linalg.norm(expected-post[-1,1:4]))
    coasts=[]
    for force in report.get('force_segments',[]):
        if force.get('center')!='Sun':continue
        a,b=force['start_jd_tdb'],force['end_jd_tdb'];rows=data[(data[:,0]>=a-1e-8)&(data[:,0]<=b+1e-8)]
        if len(rows)<2:continue
        distances=np.linalg.norm(rows[:,1:4],axis=1)/AU;i=int(np.argmin(distances));conic=heliocentric_orbit_summary(rows[0,1:],rows[0,0])
        coasts.append(dict(start_date=calendar(a),end_date=calendar(b),start_radius_au=float(distances[0]),sampled_minimum_radius_au=float(distances[i]),sampled_minimum_date=calendar(rows[i,0]),
                           initial_radial_velocity_kms=conic['radial_velocity_kms'],osculating_perihelion_au=conic.get('perihelion_au'),next_perihelion_date=conic.get('next_perihelion_date')))
    inward=[c for c in coasts if c['start_radius_au']>5 and c['sampled_minimum_radius_au']<1]
    summary=dict(heliocentric_coasts=coasts,outer_to_inner_excursions=inward,candidate_id=report.get('candidate_id'),engine_version=manifest.get('engine_version') or report.get('engine_version') or 'Not recorded in supplied ZIP',
        rows=len(data),dates_strictly_increasing=True,post_flyby_months=report.get('post_flyby_months'),
        archive_final_date=calendar(post[-1,0]),post_coast_sun_only=solar_only,arrival_radius_au=float(radii[0]/AU),final_radius_au=float(radii[-1]/AU),
        minimum_outgoing_radial_velocity_kms=float(radial.min()),outbound_throughout_supplied_extension=bool(np.all(radial>0)),
        post_coast_energy_range_km2_s2=float(np.ptp(energy)),independent_kepler_endpoint_difference_km=endpoint_error,outgoing_solar_orbit=orbit,
        interpretation=('Before the final flyby, an outer-planet coast returns inside 1 AU; see heliocentric_coasts. ' if inward else '')+('After the final flyby, the supplied continuation is smoothly outbound. Its Sun-bound orbit eventually returns inward after aphelion; the flyby label does not imply solar escape.' if np.all(radial>0) and orbit['sun_bound'] else 'Inspect radial motion and solar orbital energy.'),
        scope='Read-only XYZV/state audit. Future conic illustration is Sun-only, excludes later encounters, and is not appended to the original file.')
    atomic_json(output/'audit.json',summary)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    year=lambda jd:2000+(np.asarray(jd)-2451544.5)/365.25
    fig,axes=plt.subplots(2,2,figsize=(13,8))
    ax=axes[0,0];ax.plot(data[:,1]/AU,data[:,2]/AU,color='#6b8cac',lw=1,label='Supplied trajectory')
    ax.plot(post[:,1]/AU,post[:,2]/AU,color='#d99527',lw=2,label=str(report.get('post_flyby_months',''))+'-month extension')
    ax.scatter([0],[0],color='#d99527',s=25,label='Sun');ax.scatter([initial[0]/AU],[initial[1]/AU],s=30,color='#308e88',label='Ixion encounter')
    ax.set(xlabel='Ecliptic X (AU)',ylabel='Ecliptic Y (AU)',title='Actual addon states');ax.axis('equal');ax.legend(fontsize=8)
    ax=axes[0,1];ax.plot(year(post[:,0]),radii/AU,color='#d99527')
    ax.set(xlabel='Year (TDB, approximate)',ylabel='Distance from Sun (AU)',title='Supplied extension keeps moving outward')
    ax=axes[1,0];ax.plot(year(post[:,0]),radial,color='#308e88');ax.axhline(0,color='#64748b',lw=.8)
    ax.set(xlabel='Year (TDB, approximate)',ylabel='Outward radial speed (km/s)',title='Positive radial speed throughout')
    ax=axes[1,1];ax.plot(year(data[:,0]),np.linalg.norm(data[:,1:4],axis=1)/AU,color='#6b8cac',label='Supplied data')
    future_end=orbit.get('next_aphelion_jd_tdb',post[-1,0]+20*365.25)+10*365.25
    times=np.linspace(post[0,0],future_end,400)
    radius=np.array([np.linalg.norm(kepler(initial[:3],initial[3:],float((t-post[0,0])*DAY))[0])/AU for t in times])
    ax.plot(year(times),radius,'--',color='#d99527',label='Illustrative Sun-only continuation')
    if orbit.get('next_aphelion_jd_tdb'):
        ax.scatter(year(orbit['next_aphelion_jd_tdb']),orbit['aphelion_au'],color='#b35f48',s=25)
        ax.annotate('Aphelion '+str(round(orbit['aphelion_au'],2))+' AU\n'+orbit['next_aphelion_date'][:10],(year(orbit['next_aphelion_jd_tdb']),orbit['aphelion_au']),xytext=(-145,-45),textcoords='offset points',fontsize=9)
    ax.set(xlabel='Year (TDB, approximate)',ylabel='Distance from Sun (AU)',title='A bound orbit can eventually return');ax.legend(fontsize=8)
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle('Addon flyby audit — '+str(summary['candidate_id']),fontsize=15);fig.tight_layout()
    fig.savefig(output/'ixion_audit.png',dpi=170);plt.close(fig)
    (output/'README.md').write_text('Ixion addon audit\n\n'+summary['interpretation']+'\n\n'+json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2),flush=True)
    return summary
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.archive,a.output)
