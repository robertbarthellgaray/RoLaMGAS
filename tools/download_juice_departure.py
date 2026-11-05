"""Download official JUICE launch states and regenerate offline departure seeds.

Run from any folder: python tools/download_juice_departure.py --output departure_seeds
Network is used only by this tool, never by the search worker.
"""
from pathlib import Path
import argparse,csv,io,json,sys,urllib.parse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
from network import request_json
from ephemeris import jd,BODIES
from earth_return_seeds import hyperbolic_departure,rtn_basis
import numpy as np

BASE='https://ssd.jpl.nasa.gov/api/horizons.api'
EPOCHS=['2023-04-16T12:00:00','2023-04-17T12:00:00','2023-04-19T12:00:00']
# Horizons' mission header quotes launch only to the minute: 12:14 UTC.
# This reference epoch is that minute plus approximate TDB-UTC =69.185s.
LAUNCH='2023-04-14T12:15:09.185'

def query(command,center,times):
    p=dict(format='json',COMMAND="'"+command+"'",CENTER="'"+center+"'",MAKE_EPHEM="'YES'",EPHEM_TYPE="'VECTORS'",TLIST="'"+'\n'.join(str(jd(t)) for t in times)+"'",REF_PLANE="'ECLIPTIC'",REF_SYSTEM="'ICRF'",VEC_CORR="'NONE'",VEC_TABLE="'2'",OUT_UNITS="'KM-S'",CSV_FORMAT="'YES'",TIME_TYPE="'TDB'")
    url=BASE+'?'+urllib.parse.urlencode(p);response=request_json(url)
    if '$$SOE' not in response.get('result',''):raise ValueError('Horizons did not return a state vector: '+str(response.get('error','no coverage')))
    return dict(url=url,parameters=p,epochs_tdb=times,response=response)

def rows(document):
    raw=document['response']['result'].split('$$SOE')[1].split('$$EOE')[0]
    return [dict(jd_tdb=float(r[0]),position_km=[float(v) for v in r[2:5]],velocity_kms=[float(v) for v in r[5:8]]) for r in csv.reader(io.StringIO(raw)) if r]

def regenerate(folder,download=True):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    documents={}
    for name,command,center,times in [('juice_geocentric','-28','500@399',EPOCHS),('earth_heliocentric','399','500@10',[LAUNCH,*EPOCHS])]:
        p=folder/(name+'_raw.json')
        if download:p.write_text(json.dumps(query(command,center,times),indent=2)+'\n',encoding='utf-8')
        documents[name]=json.loads(p.read_text(encoding='utf-8'))
    earth=rows(documents['earth_heliocentric'])[0];state=earth['position_km']+earth['velocity_kms'];samples=[]
    for row in rows(documents['juice_geocentric']):samples.append(dict(row,**hyperbolic_departure(row['position_km'],row['velocity_kms'],BODIES['Earth'][1])))
    chosen=samples[0];direction=np.asarray(chosen['vinf_vector_kms'])/chosen['vinf_kms'];local=rtn_basis(state).T@direction
    data=dict(schema_version=1,spacecraft='JUICE',horizons_id='-28',frame='Geometric Ecliptic J2000',time_scale='TDB',units='km and km/s',
        launch_reference_jd_tdb=jd(LAUNCH),launch_reference_note='Approximate 12:14 UTC launch minute from Horizons mission header, converted with TDB-UTC approximately69.185s.',
        earth_launch_state_km_kms=state,selected=chosen,samples=samples,departure_direction_rtn=local.tolist(),
        first_earth_return_days=jd('2024-08-20T21:57:22.685')-jd(LAUNCH),
        source_urls=[v['url'] for v in documents.values()],mission_source_url='https://www.esa.int/Science_Exploration/Space_Science/Juice',
        limitations='Earth-only osculating asymptote estimate, not a definitive launch-injection reconstruction. Solar and lunar perturbations cause epoch dependence. Real JUICE uses a lunar-Earth assist; the Lambert solver omits the Moon. RTN rotation seeds later launches without copying the2023 inertial direction. User C3 bounds remain authoritative.')
    (folder/'juice_departure.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8');return data

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'departure_seeds');p.add_argument('--from-saved',action='store_true');a=p.parse_args()
    d=regenerate(a.output,not a.from_saved);print(json.dumps(dict(output=str(a.output),selected_c3=d['selected']['c3_km2_s2'],velocity_wrt_earth_kms=d['selected']['velocity_kms'],asymptotic_velocity_kms=d['selected']['vinf_vector_kms']),indent=2))

if __name__=='__main__':main()
