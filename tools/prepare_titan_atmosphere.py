"""Fetch original HASI/PDS profiles and build a labeled Titan reference CSV.

The entry profile TAB has no density values despite the fifth label column.
Use the separately archived corrected ACC density product at matching altitudes.
EOS fallback is available only by explicit request and remains clearly labeled.
"""
from pathlib import Path
import argparse,csv,hashlib,json,sys,urllib.request
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from network import tls_context
R_GAS=8.31446261815324
MOLAR_MASS=.98*.0280134+.02*.01604246
BASE='https://atmos.nmsu.edu/PDS/data/hphasi_0001/DATA/PROFILES/'

def parse_profile(raw,phase,density_by_altitude=None,allow_derived=False):
    rows=[];derived=0
    for line in raw.decode('ascii').splitlines():
        fields=[f.strip() for f in line.split(';')]
        if len(fields)<4:raise ValueError('HASI row has fewer than four required columns')
        _,altitude,pressure,temperature=map(float,fields[:4])
        density=float(fields[4]) if len(fields)>4 and fields[4] else None
        if density is None:
            if phase!='entry':raise ValueError('Unexpected missing descent density')
            if density_by_altitude is not None and altitude in density_by_altitude:density=density_by_altitude[altitude]
            elif allow_derived:density=pressure*MOLAR_MASS/(R_GAS*temperature);derived+=1
            else:raise ValueError('Missing entry density; fetch the corrected ACC density product or explicitly request EOS fallback')
        if min(pressure,temperature,density)<=0:raise ValueError('Nonpositive atmospheric value')
        label='HASI_ACC_density' if phase=='entry' and density_by_altitude is not None and altitude in density_by_altitude else 'HASI_entry_EOS_98N2_2CH4' if phase=='entry' else 'HASI_descent_density'
        rows.append((altitude,density,temperature,pressure,label))
    return rows,derived

def build(cache,output,download=True,allow_derived=False):
    cache.mkdir(parents=True,exist_ok=True);output.mkdir(parents=True,exist_ok=True)
    rows=[];sources=[];density_by_altitude={}
    for extension in ('.LBL','.TAB'):
        filename='HASI_L4_ACCE_DENSITY'+extension;path=cache/filename;url=BASE.replace('/PROFILES/','/ACC/')+filename
        if not path.exists():
            if not download:raise FileNotFoundError(path)
            with urllib.request.urlopen(url,context=tls_context(),timeout=60) as response:raw=response.read()
            path.write_bytes(raw)
        raw=path.read_bytes();sources.append(dict(url=url,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
        if extension=='.TAB':
            for line in raw.decode('ascii').splitlines():
                _,altitude,density=map(float,line.split(';'))
                if density<=0:raise ValueError('Invalid archived accelerometer density')
                density_by_altitude[altitude]=density
    for phase,stem in [('entry','HASI_L4_ATMO_PROFILE_ENTRY'),('descent','HASI_L4_ATMO_PROFILE_DESCEN')]:
        for extension in ('.LBL','.TAB'):
            filename=stem+extension;path=cache/filename
            if not path.exists():
                if not download:raise FileNotFoundError(path)
                with urllib.request.urlopen(BASE+filename,context=tls_context(),timeout=60) as response:raw=response.read()
                path.write_bytes(raw)
            raw=path.read_bytes();sources.append(dict(url=BASE+filename,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
        parsed,derived=parse_profile((cache/(stem+'.TAB')).read_bytes(),phase,density_by_altitude,allow_derived);rows.extend(parsed)
        print(phase,len(parsed),'rows;',derived,'densities explicitly derived from pressure and temperature')
    rows.sort(key=lambda row:row[0])
    if any(b[0]<=a[0] for a,b in zip(rows,rows[1:])):raise ValueError('Overlapping/duplicate HASI altitudes require explicit treatment')
    with (output/'hasi_reference.csv').open('w',newline='',encoding='utf-8') as stream:
        w=csv.writer(stream);w.writerow(['altitude_m','density_kg_m3','temperature_k','pressure_pa','source']);w.writerows(rows)
    metadata=dict(model='Huygens HASI 2005 reference column; corrected archived ACC entry density and descent density',dataset='HP-SSA-HASI-2-3-4-MISSION-V1.1',
        range_altitude_m=[rows[0][0],rows[-1][0]],rows=len(rows),sources=sources,archived_upper_density_samples=len(density_by_altitude),eos_fallback_rows=sum('EOS' in row[4] for row in rows),
        data_caveat='The entry profile TAB lacks density despite its label. Its 911 upper samples use the corrected HASI_L4_ACCE_DENSITY.TAB product at exactly matching altitudes; 1,816 lower samples retain the descent density product. No EOS-derived densities are needed in the bundled baseline.',
        interpolation='PCHIP of log density and log pressure; PCHIP temperature. The 146.797–157.3182 km gap is interpolated, not measured. Below the lowest 3 m, hold the lowest profile value to the surface.',
        limitations=['A single 2005 reference column, not a forecast of Titan weather in 2034/2035.','No measured wind column is supplied here; baseline winds are zero relative to rigid corotation.','Archived entry densities are instrument-team retrievals from accelerometer deceleration; they inherit the original retrieval assumptions.','No uncertainty distribution is inferred from this single profile. Density scalings are sensitivity cases, not confidence intervals.'],
        gram_upgrade='Titan-GRAM 2026 is available by request from https://software.nasa.gov/software/MFS-33888-1 ; CSV profiles can replace this reference column.')
    (output/'hasi_reference.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    return metadata

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,default=ROOT/'cache/huygens_hasi');p.add_argument('--output',type=Path,default=ROOT/'model_assets/titan');p.add_argument('--offline',action='store_true');p.add_argument('--allow-derived-entry-density',action='store_true');a=p.parse_args();build(a.cache,a.output,not a.offline,a.allow_derived_entry_density)
