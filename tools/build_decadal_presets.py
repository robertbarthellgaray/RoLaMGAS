"""Create editable app presets from cited Decadal starting guesses, not solutions."""
from pathlib import Path
import json,re,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mission_search import normalize,load_database,resolve_route
from search_options import export_options
from ephemeris import atomic_json
ROOT=Path(__file__).resolve().parents[1]

def main():
    missions=json.loads((ROOT/'departure_seeds/decadal_missions.json').read_text(encoding='utf-8'))['missions']
    db=load_database()
    for m in missions:
        if not m['seed_eligible']:continue
        dates=m.get('dates');route=resolve_route(m['sequence'],db,m.get('target_object'))
        settings=dict(target=m['bodies'][-1],target_object=m.get('target_object'),sequences=[m['sequence']],
            launch_start=dates[0] if dates else m['launch_start'],launch_end=dates[0]+'T23:59:59' if dates else m['launch_end']+'T23:59:59',
            min_c3=5,max_c3=max(30,m['c3']*1.25),max_years=max(15,sum(m['planet_leg_days'])/365.25+1),
            max_dsm_kms=max(.7,m.get('reference_dsm_total_kms',.7)),max_single_dsm_kms=.7,
            max_powered_flyby_kms=.2,powered_flybys=False,max_arrival_vinf_kms=max(15,m.get('vinf',0)*1.25),
            route_overrides={m['sequence']:dict(leg_days=route['leg_days'],branch_options=route['branch_options'])})
        if dates:settings['event_windows']=[[d+'T00:00:00',d+'T23:59:59'] for d in dates]
        config=export_options(normalize(settings))['document']['settings']
        slug=re.sub('[^a-zA-Z0-9]+','_',m['name']).strip('_')
        atomic_json(ROOT/'examples'/('decadal_'+slug+'.json'),config)
        print(m['name'],flush=True)

if __name__=='__main__':main()
