"""Check retained integrated files against cached JPL planet positions."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from scipy.optimize import minimize_scalar
from ephemeris import Ephemerides,BODIES,DAY,JD0

def audit(catalog,cache,identifiers=None):
    index=json.loads((catalog/'data/index.json').read_text(encoding='utf-8'));reports={}
    for item in index['cases']:
        if not item['spotlight']:continue
        if identifiers is not None and item['id'] not in identifiers:continue
        file=catalog/'data/cases'/(item['id']+'.json');case=json.loads(file.read_text(encoding='utf-8'))
        data=np.loadtxt(catalog/case['download'],comments='#');assert np.isfinite(data).all()
        assert np.all(np.diff(data[:,0])>=0)
        ep=Ephemerides(cache,list(BODIES),data[0,0]-.001,data[-1,0]+.001,1.)
        splits=[0]+(np.where(np.diff(data[:,0])<=0)[0]+1).tolist()+[len(data)]
        clearances={};same_epoch=[]
        for i in np.where(np.diff(data[:,0])==0)[0]:
            position_jump=float(np.linalg.norm(data[i+1,1:4]-data[i,1:4]));assert position_jump<.1
            same_epoch.append(dict(jd=float(data[i,0]),position_jump_km=position_jump,velocity_jump_mps=float(np.linalg.norm(data[i+1,4:7]-data[i,4:7])*1000)))
        for lo,hi in zip(splits[:-1],splits[1:]):
            a=data[lo:hi]
            if len(a)<2:continue
            t=(a[:,0]-JD0)*DAY;craft=CubicHermiteSpline(t,a[:,1:4],a[:,4:7],extrapolate=False)
            for body in list(BODIES)+['Sun']:
                planet=ep.splines.get(body)
                delta=a[:,1:4]-(planet(t) if planet else 0)
                distances=np.linalg.norm(delta,axis=1);j=int(np.argmin(distances))
                def distance(s):return float(np.linalg.norm(craft(s)-(planet(s) if planet else 0)))
                left=t[max(0,j-1)];right=t[min(len(t)-1,j+1)]
                fit=minimize_scalar(distance,bounds=(left,right),method='bounded',options={'xatol':.001})
                choices=[(float(distances[j]),float(t[j])),(distance(left),float(left)),(distance(right),float(right)),(float(fit.fun),float(fit.x))]
                radius,epoch=min(choices)
                surface=695700. if body=='Sun' else BODIES[body][2]
                if body not in clearances or radius<clearances[body]['radius_km']:
                    clearances[body]=dict(radius_km=radius,altitude_km=radius-surface,jd_tdb=JD0+epoch/DAY)
        assert all(c['altitude_km']>0 for c in clearances.values()),clearances
        report=dict(passed=True,method='Continuous Hermite reconstruction of the existing XYZV, with local closest-approach refinement against cached JPL planet-center ephemerides',
                    sample_count=len(data),planet_clearances=clearances,same_epoch_impulses=same_epoch,
                    scope='Solar and eight-planet surface clearance; moon encounters and navigation uncertainty are not part of this interplanetary audit')
        case['integration_validation']=report
        file.write_text(json.dumps(case,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
        reports[item['id']]=report
        print(item['id'],'all eight planets and Sun clear; closest altitude',min(c['altitude_km'] for c in clearances.values()),'km',flush=True)
    file=catalog/'data/catalog_audit.json';doc=json.loads(file.read_text(encoding='utf-8'));doc.setdefault('integrated_clearance_audits',{}).update(reports)
    file.write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--catalog',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--case',action='append');a=p.parse_args();audit(a.catalog,a.cache,a.case)
