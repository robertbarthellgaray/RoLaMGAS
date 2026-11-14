"""Add clearly labeled atmospheric reference downloads to the existing gallery case."""
from pathlib import Path
import sys,json,shutil,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    case_path=ROOT/'docs/data/cases/dragonfly-titan-entry-2035.json';case=json.loads(case_path.read_text())
    folder=ROOT/'runs/titan_entry/site_reference_descent';site=ROOT/'runs/dragonfly_titan_site';report=json.loads((folder/'entry_report.json').read_text());moon=json.loads((site/'moon_report.json').read_text())
    assert report['completed'] and report['outcome']=='illustrative_lander_release'
    assert report['atmosphere']['sha256']==hashlib.sha256((ROOT/'model_assets/titan/hasi_reference.csv').read_bytes()).hexdigest()
    assert report['full_trajectory_join']['position_join_error_km']<.01 and report['full_trajectory_join']['velocity_join_error_kms']<1e-6
    base='downloads/dragonfly-titan-entry-2035-reference';products=[
        (site/'trajectory.xyzv','-cruise-to-interface.xyzv','Separate variant: cruise to Selk-reference entry subpoint XYZV ↓'),
        (site/'arrival_state.json','-input-state.json','Atmospheric integrator input state ↓'),
        (folder/'titan_entry.xyzv','-titan-centered.xyzv','Illustrative descent XYZV · Titan-centered ↓'),
        (folder/'full_trajectory.xyzv','-full-heliocentric.xyzv','Cruise + illustrative descent XYZV · Sun-centered ↓'),
        (folder/'entry_profile.csv','-profile.csv','Atmospheric entry/descent diagnostics CSV ↓'),
        (folder/'entry_report.json','-report.json','Reference entry model and assumptions ↓'),
        (folder/'entry_profile.png','-profile.png','Entry/descent graphs'),
        (folder/'ground_track.png','-groundtrack.png','Rotating-frame ground track'),
    ]
    existing=[item for item in case.get('additional_downloads',[]) if not item['url'].startswith(base)]
    files=[]
    for source,suffix,label in products:
        target=base+suffix;destination=ROOT/'docs'/target
        if suffix.endswith('.csv'):
            destination.write_text(source.read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
        else:shutil.copy2(source,destination)
        existing.append(dict(label=label,url=target));files.append(dict(url=target,sha256=hashlib.sha256(destination.read_bytes()).hexdigest()))
    note=('Separate atmospheric reference variant: entry-interface subpoint targeted to 4 degrees N, 162.5 degrees E, in November 2035. Its cruise targeting correction is '+f"{moon['upstream_delta_v_kms']*1000:.3f} m/s, with {moon['total_onboard_delta_v_kms']*1000:.3f} m/s total onboard cruise delta-v. "+
          'The full heliocentric file uses that separate cruise variant; it is not the unchanged baseline case above. The Titan-centered file contains only atmospheric entry and descent. '+
          'Archived Huygens density profile; constant-beta aeroshell, published 2025 chute dimensions and assumed drag coefficients. Stops at 800 m lander release; does not model powered flight or touchdown. '+
          f"Model release location {report['final_location']['latitude_deg']:.3f} degrees N, {report['final_location']['longitude_east_deg']:.3f} degrees E, after {report['duration_seconds']/60:.2f} minutes. "+
          f"Predicted peak aerodynamic deceleration {report['peak_sensed_deceleration']['sensed_deceleration_g0']:.2f} Earth g, compared with the published Dragonfly study limit of 12 g; this simplified model is not a survivability validation. "+
          'This shows that an entry subpoint over the intended site does not deliver a landing there. The model is not validated as the operational Dragonfly EDL trajectory. See TITAN_ENTRY.md and studies/titan_entry/validation.json in the source repository.')
    notes=base+'-NOTES.txt';(ROOT/'docs'/notes).write_text(note+'\n',encoding='utf-8');existing.append(dict(label='Atmospheric variant file notes ↓',url=notes))
    case['additional_downloads']=existing;case['atmospheric_variant']=dict(note=note,files=files,completed=True,official_trajectory=False,landing_model_validated=False,release_altitude_m=800.,banner='Atmospheric files are a separate illustrative variant using assumed drag coefficients; they are not a validated Dragonfly EDL profile. Read the variant notes before using them.')
    case_path.write_text(json.dumps(case,separators=(',',':')),encoding='utf-8')
    print('Published atmospheric reference downloads for',case['id'])

if __name__=='__main__':main()
