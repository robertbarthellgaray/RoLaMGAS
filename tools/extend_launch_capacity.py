"""Attach explicit capacity estimates to C3=200; preserve published samples.

Models are planning approximations, not certified launch feasibility. No network.
"""
from pathlib import Path
import argparse,csv,json,math,sys
import numpy as np
from scipy.optimize import least_squares,brentq
ROOT=Path(__file__).resolve().parents[1]
MU,RP=398600.4418,6578.137
ESCAPE2=2*MU/RP
MOTOR_SOURCE='https://cdn.northropgrumman.com/-/media/Project/Northrop-Grumman/ngc/what-we-do/space/launch-vehicles/minotaur/Minotaur-IV-V-VI-User-Guide.pdf'
ISP_SOURCE='https://ntrs.nasa.gov/api/citations/20240015535/downloads/JANNAF%209871%20Propellants%20for%20Space%20Kibbey.pdf'


def velocity(c3):return np.sqrt(ESCAPE2+np.asarray(c3))


def evaluate(model,c3):
 if not model['c3_range'][0]<=c3<=model['c3_range'][1]:return None
 v=float(velocity(c3))
 if model['kind']=='effective_exponential':
  value=model['amplitude_kg']*math.exp(-(v-model['reference_speed_km_s'])/model['effective_exhaust_speed_km_s'])-model['effective_inert_mass_kg']
 elif model['kind']=='effective_stage':
  denominator=math.expm1((v-model['velocity_offset_km_s'])/model['effective_exhaust_speed_km_s'])
  if denominator<=0:return None
  value=model['propellant_kg']/denominator-model['effective_inert_mass_kg']
 else:raise ValueError('Unknown model')
 return max(0.,float(value))


def stage_anchor(c3,payload,propellant,inert,ve,assumptions):
 offset=float(velocity(c3))-ve*math.log1p(propellant/(inert+payload))
 return dict(kind='effective_stage',c3_range=[0,200],velocity_offset_km_s=offset,
             propellant_kg=propellant,effective_inert_mass_kg=inert,
             effective_exhaust_speed_km_s=ve,assumptions=assumptions)


def model_for(row):
 points=np.array(row['points'],dtype=float)
 common='Extrapolated engineering estimate. Source samples remain unchanged; not a provider guarantee. Zero means this model predicts no positive delivered payload, not a certified impossibility. No extrapolation beyond C3=200.'
 if row.get('international_id')=='nsil2025_lvm3_estimate':
  p=row['model_parameters']
  model=dict(kind='effective_stage',c3_range=[0,200],velocity_offset_km_s=p['effective_velocity_offset_km_s'],propellant_kg=p['assumed_propellant_kg'],effective_inert_mass_kg=p['fitted_effective_inert_mass_kg'],effective_exhaust_speed_km_s=p['assumed_effective_exhaust_speed_km_s'],assumptions='Extends the same NSIL-calibrated effective C25 model; all original source observations have negative C3. Model output is clipped at zero payload.')
 elif len(points)==1:
  if row.get('international_id')=='wang2025_lm5_point':
   model=stage_anchor(*points[0],26500.,3400.,4.334,
    'Single-point scenario, not a fitted performance curve: assumed 26.5 t propellant, 3.4 t effective inert mass, 4.334 km/s exhaust velocity. Upper-stage parameters follow the comparison table in Upper Stage Liquid Propellant Rocket Engine: A Case Analysis; configuration and losses are not independently validated.')
   model['assumption_sources']=['https://www.scielo.br/j/jatm/a/jg5XF3Ls6mb98g9WXwVK3Zw/']
  elif row.get('published_id','').startswith('ariane6'):
   model=stage_anchor(*points[0],30000.,4500.,4.5,
    'Single-point scenario: 30 t upper-stage propellant is published by ESA; 4.5 t effective inert mass and 4.5 km/s effective exhaust velocity are explicitly analyst assumptions, not manufacturer ratings. Calibrates only the velocity offset to the 2021 manual point; not a unique curve.')
   model['assumption_sources']=['https://www.esa.int/articles/about-us/directorates/space-transportation/ariane/ariane-6-what-s-it-made-of']
  else:return None
 else:
  # A bounded effective rocket-equation shape, fitted only to the highest-energy samples.
  pts=points[-min(5,len(points)):];v=velocity(pts[:,0]);mass=pts[:,1];vref=float(v[0])
  def residual(x):return x[0]*np.exp(-(v-vref)/x[2])-x[1]-mass
  fit=least_squares(residual,[mass[0]+5000,5000,4.0],bounds=([mass[0],0.,2.5],[1e6,1e6,6.0]),max_nfev=3000,xtol=1e-12,ftol=1e-12,gtol=1e-12)
  if not fit.success:raise ValueError('Capacity fit failed: '+row['vehicle'])
  model=dict(kind='effective_exponential',c3_range=[0,200],amplitude_kg=float(fit.x[0]),effective_inert_mass_kg=float(fit.x[1]),effective_exhaust_speed_km_s=float(fit.x[2]),reference_speed_km_s=vref,
             fitted_c3_range=[float(pts[0,0]),float(pts[-1,0])],fit_rms_kg=float(np.sqrt(np.mean(fit.fun**2))),
             assumptions='Empirical effective rocket-equation shape fitted to the last up to five supplied capacity samples. Exhaust-speed parameter bounded to 2.5–6 km/s; it and inert mass are fit parameters, not identified hardware. Assumes a 200 km reference perigee and unchanged vehicle configuration. Accuracy outside source coverage is unvalidated.')
 model.update(note=common,source_c3_range=[float(points[0,0]),float(points[-1,0])])
 return model


def kickstage_rows(vehicles):
 # Published motor-only masses; a separate integration allowance remains explicit.
 wet,dry,ve,adapter,loss=2171.,157.,292.1*9.80665/1000,100.,.1
 rows=[]
 for parent in vehicles:
  if parent.get('international_id') or parent.get('published_id'):continue
  points=np.array(parent['points'],dtype=float)
  samples=[];choices=[]
  for target in range(100,201):
   # Fixed full-propellant kick must produce the requested C3, not merely exceed it.
   def required_payload(c):
    needed=float(velocity(target)-velocity(c))+loss
    ratio=math.exp(needed/ve)
    return (wet+adapter-ratio*(dry+adapter))/(ratio-1)
   def margin(c):return required_payload(c)-(np.interp(c,points[:,0],points[:,1])-wet-adapter)
   lo=float(points[0,0]);hi=min(float(points[-1,0]),float(target));best=0.;selected=None
   if margin(lo)<=0:
    selected=hi if margin(hi)<=0 else brentq(margin,lo,hi,xtol=1e-10)
    best=max(0.,required_payload(selected))
    if best==0:selected=None
   samples.append([float(target),best]);choices.append(selected)
  row=dict(kickstage_id='star48bv_'+parent['vehicle'],vehicle=parent['vehicle']+' + STAR 48BV · concept',
           launch_site=parent.get('launch_site','Source launch site'),source_label='Modeled kick-stage combination · not flight-qualified',
           source_url=MOTOR_SOURCE,data_kind='modeled_kickstage_combination',source_year=2026,
           display_rounding_kg=100,query_grid_c3=list(range(100,201)),points=samples,
           fairing=parent.get('fairing','Parent launcher configuration'),adapter='Assumed extra 100 kg kick-stage integration hardware',
           model_parameters=dict(motor_wet_mass_kg=wet,motor_dry_mass_kg=dry,motor_propellant_mass_kg=wet-dry,effective_isp_s=292.1,integration_mass_kg=adapter,assumed_kick_loss_km_s=loss,reference_perigee_altitude_km=200),
           parent_vehicle=parent['vehicle'],parent_source_url=parent.get('source_url','https://elvperf.ksc.nasa.gov/Pages/Query.aspx'),
           source_urls=[MOTOR_SOURCE,ISP_SOURCE],optimal_parent_c3=choices,
           ground_rules='Conceptual configuration, not an offered or qualified launch service. Uses only interpolated published parent-launcher samples (no parent extrapolation), optimizes their staging C3, and subtracts the 2,171 kg motor plus an assumed 100 kg integration allowance. Northrop Minotaur IV/V/VI guide PDF p.23 gives 2,014 kg propellant and 157 kg inert motor mass; NASA 20240015535 Table 1 gives effective Isp 292.1 s. Assumes a tangential kick at 200 km Earth altitude and an analyst-selected 100 m/s loss allowance; no finite-burn, structural, attitude, separation, thermal, restart or integration qualification is modeled. Values include the kick-stage mass penalty and are spacecraft payload after that modeled penalty. Model scenarios, not confidence intervals or guarantees.')
  rows.append(row)
 return rows


def extend(document):
 doc=json.loads(json.dumps(document));base=[v for v in doc['vehicles'] if not v.get('kickstage_id')]
 for row in base:
  row['extrapolation']=model_for(row)
 doc['vehicles']=base+kickstage_rows(base)
 doc['extrapolation_policy']='Explicit engineering estimates to C3=200; native source samples take precedence. No claim of validated extrapolation or offered kick-stage combinations.'
 return doc


def main():
 p=argparse.ArgumentParser(description=__doc__);p.parse_args()
 source=ROOT/'gui_assets/launch_performance_curves.json';doc=extend(json.loads(source.read_text(encoding='utf-8')))
 for path in [source,ROOT/'docs/data/launch_performance_curves.json']:
  path.write_text(json.dumps(doc,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
 study=ROOT/'studies/published_launch_performance';out=[]
 for row in doc['vehicles']:
  for c in [10,15,30,60,100,158,200]:
   if row.get('kickstage_id') and c<100:continue
   points=row['points'];exact=next((m for x,m in points if x==c),None)
   if exact is not None:m=exact;kind=row.get('data_kind','NASA sample')
   elif points[0][0]<=c<=points[-1][0]:m=float(np.interp(c,np.array(points)[:,0],np.array(points)[:,1]));kind='interpolation'
   else:m=evaluate(row['extrapolation'],c);kind='extrapolated estimate'
   out.append([row['vehicle'],c,int(round(m/100)*100) if m is not None else '',kind])
 with (study/'extended_capacity_estimates.csv').open('w',newline='',encoding='utf-8') as f:
  w=csv.writer(f);w.writerow(['vehicle','c3_km2_s2','payload_kg_rounded_100kg','basis']);w.writerows(out)
 print(json.dumps([dict(vehicle=r[0],c3=r[1],kg=r[2],basis=r[3]) for r in out if r[1] in [158,200]],indent=2))


if __name__=='__main__':main()
