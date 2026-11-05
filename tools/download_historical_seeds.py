"""Refresh reproducible historical Earth departure references from JPL Horizons.
Only this manual tool uses the network. The solver uses bundled numeric references.
Run python tools/download_historical_seeds.py [--from-saved]. Historical timing
is a seed, not a reproduction; no accepted flyby or burn is fabricated.
"""
from pathlib import Path
import argparse,json,sys,time,urllib.parse,csv,io,re
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
import numpy as np
from ephemeris import jd,BODIES
from earth_return_seeds import hyperbolic_departure,rtn_basis
from network import request_json
ROOT=Path(__file__).resolve().parents[1]

def query(command,center,epochs):
    p=dict(format='json',COMMAND="'"+command+"'",CENTER="'"+center+"'",MAKE_EPHEM="'YES'",EPHEM_TYPE="'VECTORS'",TLIST="'"+'\n'.join(str(t) for t in epochs)+"'",REF_PLANE="'ECLIPTIC'",REF_SYSTEM="'ICRF'",VEC_CORR="'NONE'",VEC_TABLE="'2'",OUT_UNITS="'KM-S'",CSV_FORMAT="'YES'",TIME_TYPE="'TDB'")
    url='https://ssd.jpl.nasa.gov/api/horizons.api?'+urllib.parse.urlencode(p)
    for attempt in range(3):
        try:
            response=request_json(url,timeout=30)
            if '$$SOE' not in response.get('result',''):raise ValueError('No spacecraft coverage: '+str(response.get('error',response.get('result','')))[:180])
            if not re.search(r'Target body name:.*\('+re.escape(command)+r'\)',response['result']):raise ValueError('Horizons target identity differs from requested ID')
            return dict(parameters=p,url=url,response=response)
        except RuntimeError:
            if attempt==2:raise
            time.sleep(1+attempt)

def rows(document):
    raw=document['response']['result'].split('$$SOE')[1].split('$$EOE')[0]
    return [dict(jd_tdb=float(r[0]),position_km=[float(v) for v in r[2:5]],velocity_kms=[float(v) for v in r[5:8]]) for r in csv.reader(io.StringIO(raw)) if r]

def regenerate(folder,download=True):
    p=folder/'historical_missions.json';data=json.loads(p.read_text(encoding='utf-8'));rawfolder=folder/'historical_raw';rawfolder.mkdir(exist_ok=True)
    for mission in data['missions']:
        dates=[jd(date) for date in mission['dates']];mission['planet_leg_days']=np.diff(dates).tolist()
        dsm=mission.get('dsm_event')
        if dsm:
            i=dsm['leg_index'];mission['dsm_fraction']=(jd(dsm['date'])-dates[i])/(dates[i+1]-dates[i])
        if not mission.get('horizons_id'):continue
        key=mission['name'].lower().replace(' ','_');launch=dates[0]+.5;times=[launch+2,launch+3,launch+5]
        try:
            docs={}
            for kind,command,center,epochs in [('geocentric',mission['horizons_id'],'500@399',times),('earth_heliocentric','399','500@10',[launch])]:
                file=rawfolder/(key+'_'+kind+'.json')
                if download:file.write_text(json.dumps(query(command,center,epochs),indent=2)+'\n',encoding='utf-8')
                docs[kind]=json.loads(file.read_text(encoding='utf-8'))
            earth=rows(docs['earth_heliocentric'])[0];earthstate=earth['position_km']+earth['velocity_kms'];samples=[]
            for row in rows(docs['geocentric']):samples.append(dict(row,**hyperbolic_departure(row['position_km'],row['velocity_kms'],BODIES['Earth'][1])))
            chosen=samples[0];local=rtn_basis(earthstate).T@(np.array(chosen['vinf_vector_kms'])/chosen['vinf_kms'])
            mission.update(departure=dict(selected=chosen,samples=samples,earth_reference_state_km_kms=earthstate,direction_rtn=local.tolist(),reference_launch_jd_tdb=launch,reference_epoch_note='Noon TDB on published launch day; approximate orientation reference, not an exact launch/separation epoch.',frame='Geometric Ecliptic J2000',time_scale='TDB',source_urls=[doc['url'] for doc in docs.values()],limitations='Earth-only outgoing osculating asymptote. Perturbations cause epoch dependence; not definitive delivered C3. Direction is rotated through the Earth RTN basis for each trial launch.'))
            mission.pop('departure_unavailable',None);print(mission['name'],'C3 estimate',round(chosen['c3_km2_s2'],6),'leg days',mission['planet_leg_days'],flush=True)
        except (ValueError,RuntimeError,FileNotFoundError) as exc:
            mission['departure_unavailable']=str(exc);mission.pop('departure',None);print(mission['name'],'timing seed only:',str(exc)[:200],flush=True)
        p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8');return data
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--from-saved',action='store_true');a=p.parse_args();regenerate(ROOT/'departure_seeds',not a.from_saved)
