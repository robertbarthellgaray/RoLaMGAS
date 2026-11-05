"""Regenerate the complete EdvEVEEJ C3/DSM seed family locally, without AI.

Example: python tools/build_low_energy_chain_seed.py --cache PATH_TO_ROLAMGAS_CACHE
All ephemerides must already exist; this tool never downloads or uploads data.
"""
from pathlib import Path
import argparse,json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
from app_paths import DATA_ROOT,RESOURCE_ROOT
from mission_search import normalize,routes_for,get_ephemerides
from earth_return_seeds import fit_initial_dsm
from dynamics import Model
from community import public_record
from ephemeris import atomic_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',type=Path,default=DATA_ROOT/'cache')
    p.add_argument('--reference',type=Path,default=RESOURCE_ROOT/'departure_seeds/eevee_chain.json')
    p.add_argument('--output',type=Path,default=RESOURCE_ROOT/'departure_seeds/eevee_chain.json')
    p.add_argument('--c3',nargs='+',type=float,default=[6.25,7.,8.,9.,10.])
    a=p.parse_args();ref=json.loads(a.reference.read_text(encoding='utf-8'))
    c=normalize(dict(target='Jupiter',sequences=['EdvEVEEJ'],launch_start='2029-01-01',launch_end='2043-01-01',
        min_c3=min(a.c3),max_c3=max(a.c3),max_dsm_kms=1.5,max_single_dsm_kms=.7,max_arrival_vinf_kms=15.,max_years=20.,
        minimum_altitude_km={'Earth':200.,'Venus':300.},cache=str(a.cache.resolve())))
    route=routes_for(c)[0];ep=get_ephemerides(c,[route]);model=Model(route,c,ep);records=[]
    for energy in a.c3:
        q=fit_initial_dsm(model,ref['donor']['dates_jd_tdb'],ref['donor']['branches'],energy)
        if q is None:raise RuntimeError(f'No passing fixed-date continuation at C3 {energy}')
        q.update(status='passes_configured_patched_conic_screen',discovered_unix=time.time())
        records.append(public_record(q,c,route))
        print(json.dumps(dict(c3=q['launch_c3_km2_s2'],dsm_mps=1000*q['total_dsm_kms'],max_mismatch_mps=q['max_vinf_mismatch_mps'])),flush=True)
    ref['candidates']=records;ref['reference_events']=[dict(body=body,julian_date_tdb=date,planet_state_km_kms=ep.state(body,date).tolist()) for body,date in zip(route['bodies'],ref['donor']['dates_jd_tdb'])]
    atomic_json(a.output,ref)
    print('Saved complete, revalidated chain seeds:',a.output,flush=True)

if __name__=='__main__':main()
