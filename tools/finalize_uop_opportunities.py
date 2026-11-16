"""Audit UOP reconstructions, write portable options, and optionally share them.

Run reconstruct_uop_opportunities.py first. --share is an explicit network write.
"""
from pathlib import Path
import argparse,contextlib,csv,io,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
import bootstrap
import numpy as np
from dynamics import Model,kepler
from ephemeris import Ephemerides,jd,atomic_json,DAY,AU,calendar,MU_SUN
from community import record_variables,exchange,encounter_key
from presentation import validate_candidate
from reconstruct_uop_opportunities import WINDOWS,OUT,FLOORS


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--site',type=Path,default=ROOT/'.build/website-pdf-export');p.add_argument('--share',action='store_true');a=p.parse_args();site=a.site
 ep=Ephemerides(ROOT/'cache',['Earth','Venus','Jupiter','Uranus'],jd('2028-01-01'),jd('2056-01-01'),1.)
 reports=[];records=[];solved=[];seeds=[];annotations=json.loads((site/'docs/data/mission_annotations.json').read_text(encoding='utf-8'))
 for spec in WINDOWS:
  date,c3,base,budget,years=spec;path=OUT/(date+'_solution.json')
  if not path.exists():
   reports.append(dict(reference_launch=date,status='Not reproduced under stated safety floors',reference_c3=c3,reference_years=years,reference_dsm_kms=budget));continue
  saved=json.loads(path.read_text(encoding='utf-8'));q=saved['candidate'];record=saved['record']
  model=Model(saved['route'],saved['config'],ep);x,bb=record_variables(record,model);check=model.evaluate(x,bb)
  if not model.accepted(check) or check['max_vinf_mismatch_mps']>.01:raise ValueError('Recomputed flyby screen failed: '+date)
  for k in ['launch_c3_km2_s2','total_dsm_kms','arrival_vinf_kms','duration_years']:
   if abs(q[k]-check[k])>1e-7:raise ValueError('Stored metric drift: '+k)
  candidate_path=OUT/(date+'.candidate.json');atomic_json(candidate_path,q)
  with contextlib.redirect_stdout(io.StringIO()):validate_candidate(candidate_path,OUT/(q['id']+'.validation.json'))
  audit=json.loads((OUT/(q['id']+'.validation.json')).read_text())
  name=f'UOP concept {date} · {q["sequence"]}'
  note=('Numerical reconstruction of UOP Exhibit 3-24 (printed p.25), not an official flight solution. '
        'Report launch date and rounded C3/time targets; intermediate epochs and DSM placement were solved independently. '
        'Unpowered flybys screened at Earth ≥200 km, Venus ≥300 km and Jupiter ≥10,000 km. '
        'Solar coasts independently integrated; finite-radius targeting, capture/UOI, probe delivery and n-body corrections are excluded.')
  annotations['missions'][record['id']]=dict(label=name,mission_kind='reconstruction',note=note,featured_priority=3)
  case=dict(id=q['id'],title=name,sequence=q['sequence'],bodies=q['bodies'],c3=q['launch_c3_km2_s2'],years=q['duration_years'],vinf=q['arrival_vinf_kms'],burns_mps=1000*q['total_dsm_kms'],desktop_record=record,
            events=[dict(jd=t) for t in q['dates_jd_tdb']],burns=[dict(kind='DSM',magnitude_mps=1000*b['magnitude_kms']) for b in q['dsms']],
            flybys=[dict(body=f['body'],altitude_floor_km=f['minimum_altitude_km']) for f in q['flybys']])
  js="import fs from 'node:fs';import {transferDocument} from './docs/desktop_transfer.js';process.stdout.write(JSON.stringify(transferDocument(JSON.parse(fs.readFileSync(0,'utf8')))));"
  options=json.loads(subprocess.run(['node','--input-type=module','-e',js],input=json.dumps(case),capture_output=True,text=True,check=True,cwd=site).stdout)
  options['settings'].update(max_c3=c3+.1,min_c3=max(5,c3-.1),max_years=years+.06,max_dsm_kms=budget+.025,max_single_dsm_kms=budget+.025,vinf_tolerance_mps=1,max_venus_c3=None)
  atomic_json(OUT/(date+'.rolamgas.json'),options)
  examples=site/'examples';atomic_json(examples/('uop_'+date+'.options.json'),options)
  # Keep full-precision encounter and burn timings in the normal app seed catalog.
  mission=dict(name=name,sequence=q['sequence'],bodies=q['bodies'],dates=[e['date'].replace(' TDB','') for e in q['events']],
               c3=q['launch_c3_km2_s2'],planet_leg_days=np.diff(q['dates_jd_tdb']).tolist(),
               seed_eligible=True,reference_kind='Recomputed UOP concept initialization; independently checked solar coasts',
               note=note+' The report maneuver budget can exceed ordinary app defaults; use the matching portable options.',
               sources=['https://science.nasa.gov/wp-content/uploads/2023/10/uranus-orbiter-and-probe.pdf'],
               dsm_events=[dict(leg_index=b['leg_index'],date=b['date'].replace(' TDB',''),fraction=(b['julian_date_tdb']-q['dates_jd_tdb'][b['leg_index']])/(q['dates_jd_tdb'][b['leg_index']+1]-q['dates_jd_tdb'][b['leg_index']]),magnitude_kms=b['magnitude_kms']) for b in q['dsms']])
  seeds.append(mission);records.append(record);solved.append((date,q))
  reports.append(dict(reference_launch=date,status='Passing Lambert reconstruction',id=record['id'],sequence=q['sequence'],launch=q['launch_date'],arrival=q['arrival_date'],reference_c3=c3,c3=q['launch_c3_km2_s2'],reference_dsm_kms=budget,dsm_kms=q['total_dsm_kms'],reference_years=years,years=q['duration_years'],arrival_vinf_kms=q['arrival_vinf_kms'],maximum_speed_gap_mps=q['max_vinf_mismatch_mps'],maximum_solar_endpoint_error_km=audit['maximum_endpoint_error_km']))
 if a.share:
  receipts=[]
  for i in range(0,len(records),10):receipts.append(exchange('https://rolamgas-community.corigarayv.workers.dev/v1/candidates',dict(candidates=records[i:i+10])))
  atomic_json(OUT/'publication_receipt.json',receipts)
  # Resolve near-duplicate winners so display names follow the visible public record.
  for r in records:
   data=exchange('https://rolamgas-community.corigarayv.workers.dev/v1/candidates?resolve_id='+r['id'])
   found=[data['candidate']] if data.get('candidate') else data.get('candidates',[])
   if found:
    winner=found[0];annotations['missions'][winner['id']]=annotations['missions'][r['id']]
   else:raise ValueError('Submitted record could not be resolved: '+r['id'])
 for path in [site/'community_seed_catalog.json',site/'docs/data/community_seed_catalog.json']:
  doc=json.loads(path.read_text(encoding='utf-8'));old={r['id']:r for r in doc['candidates']};old.update({r['id']:r for r in records});doc['candidates']=list(old.values());path.write_text(json.dumps(doc,separators=(',',':'))+'\n',encoding='utf-8')
 doc=json.loads((site/'departure_seeds/mission_studies.json').read_text(encoding='utf-8'));names={m['name'] for m in seeds};doc['missions']=[m for m in doc['missions'] if m['name'] not in names]+seeds;atomic_json(site/'departure_seeds/mission_studies.json',doc)
 atomic_json(site/'docs/data/mission_annotations.json',annotations)
 atomic_json(OUT/'comparison.json',reports)
 with (OUT/'comparison.csv').open('w',newline='',encoding='utf-8') as f:
  fields=list(dict.fromkeys(k for r in reports for k in r));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(reports)
 study=site/'studies/uop_opportunities_2026';study.mkdir(exist_ok=True)
 atomic_json(study/'comparison.json',reports);(study/'comparison.csv').write_bytes((OUT/'comparison.csv').read_bytes())
 # Consistent review gallery: full cruise in the ecliptic; physical flyby geometry is screened separately.
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(4,4,figsize=(17,17))
 lookup=dict(solved)
 for ax,spec in zip(axes.flat,WINDOWS):
  date=spec[0];q=lookup.get(date)
  if q is None:ax.text(.5,.5,'Not reproduced\nunder current safety floors',ha='center',va='center',transform=ax.transAxes);ax.set_title(date);ax.set_axis_off();continue
  for s in q['segments']:
   from scipy.integrate import solve_ivp
   duration=(s['end_jd']-s['start_jd'])*DAY
   fit=solve_ivp(lambda t,y:np.r_[y[3:],-MU_SUN*y[:3]/np.linalg.norm(y[:3])**3],(0,duration),np.r_[s['r'],s['v']],method='DOP853',rtol=2e-12,atol=1e-7,t_eval=np.linspace(0,duration,180))
   if not fit.success:raise ValueError(fit.message)
   points=fit.y[:3].T/AU
   ax.plot(points[:,0],points[:,1],lw=.9)
  pts=np.array([e['planet_state_km_kms'][:3] for e in q['events']])/AU
  ax.scatter(pts[:,0],pts[:,1],s=10);ax.scatter([0],[0],color='orange',s=15);ax.set_aspect('equal',adjustable='datalim');ax.grid(alpha=.2)
  ax.set_title(f"{date} · {q['sequence']}\nC3 {q['launch_c3_km2_s2']:.2f} · {q['duration_years']:.2f} yr\nDSM {q['total_dsm_kms']*1000:.0f} m/s",fontsize=9)
 fig.suptitle('UOP Exhibit 3-24: independently reconstructed opportunities',fontsize=16);fig.tight_layout(rect=(0,0,1,.98));fig.savefig(study/'overview.png',dpi=130);plt.close(fig)
 lines=['# UOP launch-opportunity reconstructions','','Source: Uranus Orbiter and Probe mission concept report, Exhibit 3-24, printed p.25 (PDF p.31).',
        '',f'{len(records)} of 16 reference opportunities have passing reconstructions. Launch calendar days match; C3 and flight times are compared to rounded report values. These are independently solved trajectories, not recovered official state histories.',
        '', 'The two unresolved windows remain explicitly marked; their sub-floor periapses are not published as passing. Earth ≥200 km, Venus ≥300 km and Jupiter ≥10,000 km are retained.',
        '', 'Checks: full-chain re-evaluation, flyby speed mismatch below 0.01 m/s and independent DOP853 solar propagation. Capture/UOI, finite-radius export corrections and n-body propagation are not included. Report UOI costs and post-capture masses were not recreated.',
        '', 'Some reference DSMs exceed the ordinary 700 m/s cap. Each `examples/uop_DATE.options.json` carries the appropriate explicit study budget and the full candidate. The community library also supplies the passing routes to installed clients without a binary update.',
        '', '| Reference launch | Sequence | C3 | DSM m/s | Years | Status |','|---|---|---:|---:|---:|---|']
 for r in reports:lines.append(f"| {r['reference_launch']} | {r.get('sequence','—')} | {r.get('c3',0):.2f} | {r.get('dsm_kms',0)*1000:.1f} | {r.get('years',0):.3f} | {r['status']} |")
 lines.extend(['','![Trajectory overview](overview.png)','','Re-run locally: `python tools/reconstruct_uop_opportunities.py --workers 3`, then `python tools/finalize_uop_opportunities.py --site PATH_TO_REPO` after reviewing the results. The search requires cached one-day Earth/Venus/Jupiter/Uranus JPL coverage over 2028–2056 and a saved Uranus library snapshot at the run directory. `--share` is required to write to the public service.'])
 (study/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps(dict(passing=len(records),unresolved=[r['reference_launch'] for r in reports if 'id' not in r],max_endpoint_error_km=max(r.get('maximum_solar_endpoint_error_km',0) for r in reports)),indent=2))

if __name__=='__main__':main()
