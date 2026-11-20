"""Moon branch safety, impulse accounting, and worker lifecycle contracts."""
import bootstrap  # noqa: F401
import csv,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import numpy as np
from ephemeris import DAY
from moon_targets import validate_options,target_options,named_moon
from moon_targeting import finite_source,retained_burns,stitch_source,optimize_correction_timing,selected_arrival_epoch
from moon_targets import titan_body_axes,titan_target_normal,titan_geography

class MoonTargetingTests(unittest.TestCase):
    def test_moon_keeps_selected_arrival_even_if_finite_export_shifted_the_planet_date(self):
        self.assertEqual(selected_arrival_epoch(dict(dates_jd_tdb=[2451545.,2463165.]),dict(final_encounter_jd_tdb=2463166.)),2463165.)
        self.assertEqual(selected_arrival_epoch({},dict(final_encounter_jd_tdb=2463166.)),2463166.)
        with self.assertRaises(ValueError):selected_arrival_epoch(dict(dates_jd_tdb=[]),{})
        with self.assertRaises(ValueError):selected_arrival_epoch(dict(dates_jd_tdb=[float('nan')]),{})
    def test_local_ephemeris_steps_preserve_sub_julian_date_precision(self):
        from scipy.interpolate import CubicHermiteSpline
        from moon_targeting import BodyVectors
        from moon_arrival import elapsed_position
        from ephemeris import JD0
        epoch=2463165.;center=(epoch-JD0)*DAY
        spline=CubicHermiteSpline([center-1,center+1],[[0,0,0],[26,0,0]],[[13,0,0],[13,0,0]])
        ep=Mock(splines={'Europa':spline});body=BodyVectors(ep,'Europa')
        # A 10-microsecond ODE substep is smaller than the representable JD tick.
        delta=elapsed_position(body,epoch,.00001)-elapsed_position(body,epoch,0.)
        self.assertGreater(delta[0],.00012);self.assertLess(delta[0],.00014)

    def test_europa_selection_is_a_jupiter_search_and_survives_options_export(self):
        from mission_search import normalize
        from search_options import export_options,import_options
        self.assertTrue({'Europa','Io','Ganymede','Callisto'}.issubset({m['name'] for m in target_options('Jupiter')}))
        config=dict(target='Jupiter',sequences=['EJ'],moon_target=dict(parent='Jupiter',moon_id='502',gm='untrusted'))
        normalized=normalize(config)
        self.assertEqual(normalized['moon_target'],dict(parent='Jupiter',moon_id='502',moon_name='Europa'))
        imported=import_options(export_options(config)['document'])['config']
        self.assertEqual(imported['moon_target'],normalized['moon_target'])
        with self.assertRaises(ValueError):normalize(dict(config,target='Saturn'))
        with self.assertRaises(ValueError):normalize(dict(config,moon_target=dict(parent='Jupiter',moon_id='606')))
        for parent in ('Mars','Uranus','Neptune'):
            moon=target_options(parent)[0]
            self.assertEqual(validate_options(parent,moon['id'],'impact',0)['parent'],parent)

    def test_known_moon_alias_resolves_offline_without_becoming_a_small_body(self):
        from gui import App
        with tempfile.TemporaryDirectory() as temp,patch('gui.HERE',Path(temp)),patch('gui.resolve') as remote:
            app=App();europa=app.lookup('Europa (JII)','2030-01-01')
            self.assertEqual(europa['id'],'502');self.assertEqual(europa['parent_body'],'Jupiter')
            self.assertEqual(europa['kind'],'natural_satellite');remote.assert_not_called()
        self.assertEqual(named_moon('SPK=502')['name'],'Europa')
        self.assertIsNone(named_moon('52 Europa'))
        self.assertIsNone(named_moon('20000502'))

    def test_timing_refinement_improves_scan_and_stays_before_soi(self):
        options=validate_options('Jupiter','502','impact',0)
        seeds=[]
        def solve(segment,arrival,parent,moon,base,fraction,system,progress,inclination_deg=None):
            seeds.append(dict(base))
            report=dict(upstream_burn_fraction=fraction,upstream_burn_jd_tdb=2451545+fraction*100,
                        upstream_delta_v_kms=.01+(fraction-.43)**2,entry_jd_tdb=2451624.,
                        state_before_soi_burn_saturn_relative_km_kms=[1,2,3,4,5,6])
            return report,np.zeros(2),np.zeros((2,6))
        with patch('moon_targeting.target_upstream',side_effect=solve):
            best,attempts=optimize_correction_timing(dict(start_jd=2451545),2451645,None,None,dict(entry_jd_tdb=2451625),options,None,lambda *a,**k:None,lambda:False)
        scan=min(a['delta_v_mps'] for a in attempts if a['stage']=='scan')
        self.assertLess(best[0]*1000,scan)
        self.assertEqual(seeds[0]['entry_jd_tdb'],2451625.)
        self.assertEqual(seeds[1]['entry_jd_tdb'],2451624.)
        self.assertLess(abs(best[1]['upstream_burn_fraction']-.43),.015)
        self.assertTrue(all(100+a['fraction']*100<179 for a in attempts))
        with self.assertRaises(InterruptedError):
            optimize_correction_timing(dict(start_jd=100),200,None,None,dict(entry_jd_tdb=180),options,None,lambda *a,**k:None,lambda:True)

    def test_rotating_titan_point_is_fixed_on_surface_and_moves_in_inertial_space(self):
        epoch=2464659.3516917247;latitude,longitude=4.,162.5
        axes=titan_body_axes(epoch);np.testing.assert_allclose(axes@axes.T,np.eye(3),atol=1e-14)
        position=3844.76*titan_target_normal(epoch,latitude,longitude)
        pole=axes[2];omega=np.radians(22.5769768)/DAY*pole
        result=titan_geography(epoch,np.r_[position,np.cross(omega,position)])
        self.assertAlmostEqual(result['latitude_deg'],latitude,places=11);self.assertAlmostEqual(result['longitude_east_deg'],longitude,places=11)
        self.assertLess(result['rotating_frame_speed_kms'],1e-15)
        moved=titan_target_normal(epoch+1,latitude,longitude)
        self.assertGreater(np.linalg.norm(moved-position/3844.76),.3)
        # At J2000 the prime meridian has RA=RA_pole+90+W in the
        # equatorial-node construction; north must match the independent pole.
        from arrival_geometry import planet_pole
        np.testing.assert_allclose(axes[2],planet_pole('Titan',epoch),atol=1e-14)

    def test_fixed_point_rejects_overconstraint_and_airless_entry(self):
        args=dict(parent='Saturn',moon_id='606',mode='entry',altitude=1270,target_latitude_deg=4,target_longitude_deg=-197.5)
        self.assertEqual(validate_options(**args)['target_point']['longitude_east_deg'],162.5)
        with self.assertRaises(ValueError):validate_options(**dict(args,inclination_deg=90))
        with self.assertRaises(ValueError):validate_options(**dict(args,mode='approach'))
        with self.assertRaises(ValueError):validate_options(**dict(args,target_latitude_deg=91))
    def test_supported_parent_and_physical_modes(self):
        self.assertEqual(validate_options('Saturn','606','impact',-100)['altitude_km'],0.)
        self.assertEqual(validate_options('Saturn','606','entry',1270)['moon']['name'],'Titan')
        for args in [('Jupiter','606','approach',200),('Saturn','602','entry',100),('Saturn','606','approach',0),('Saturn','606','entry',float('nan'))]:
            with self.assertRaises(ValueError):validate_options(*args)
        with self.assertRaises(ValueError):validate_options('Saturn','606','approach',200,max_added_mps=float('inf'))
        self.assertEqual(validate_options('Saturn','606','entry',1270,inclination_deg=90)['inclination_deg'],90.)
        with self.assertRaises(ValueError):validate_options('Saturn','602','approach',100,inclination_deg=90)
        with self.assertRaises(ValueError):validate_options('Saturn','606','entry',1270,inclination_deg=-1)

    def test_cruise_budget_excludes_launcher_and_replaced_terminal_burns(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            with (p/'burns.csv').open('w',newline='') as f:
                w=csv.writer(f);w.writerow(['kind','julian_date_tdb','magnitude_kms']);w.writerows([['launch_injection_from_200_km',1,5.3],['retargeted_DSM',2,.4],['finite_patch_junction',3,.0001],['terminal_correction',9,.2]])
            rows,cost=retained_burns(p,5)
            self.assertEqual(len(rows),3);self.assertAlmostEqual(cost,.4001)

    def test_finite_source_uses_actual_sample_inside_last_solar_coast(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'trajectory.xyzv';rows=np.array([[t,1e8,0,0,0,30,0] for t in range(1,11)])
            np.savetxt(path,rows)
            report=dict(numerical_validation_passed=True,final_encounter_jd_tdb=10,force_segments=[dict(center='Sun',start_jd_tdb=1,end_jd_tdb=3),dict(center='Earth',start_jd_tdb=3,end_jd_tdb=4),dict(center='Sun',start_jd_tdb=4,end_jd_tdb=9)])
            segment,_,_=finite_source(path,report)
            self.assertEqual(segment['start_jd'],5);self.assertEqual(segment['v'],[0.,30.,0.])
            report['numerical_validation_passed']=False
            with self.assertRaises(ValueError):finite_source(path,report)

    def test_gui_status_reports_unexpected_exit_and_rejects_path_traversal(self):
        from gui import App
        with tempfile.TemporaryDirectory() as temp,patch('gui.HERE',Path(temp)):
            app=App();identifier='0123456789ab';branch='abcdef012345';out=app.folder('test')/'moon_targets'/identifier/branch;out.mkdir(parents=True)
            (out/'status.json').write_text(json.dumps(dict(state='running',message='solving')))
            app.moon_jobs[('test',identifier,branch)]=Mock(poll=Mock(return_value=1))
            self.assertEqual(app.moon_target_status('test',identifier,branch)['state'],'failed')
            for bad in ('../outside','not-an-id'):
                with self.assertRaises(ValueError):app.moon_target_status('test',bad,branch)
                with self.assertRaises(ValueError):app.moon_target_status('test',identifier,bad)

    def test_gui_reuses_matching_finite_export_and_stops_on_request(self):
        from gui import App
        import hashlib
        with tempfile.TemporaryDirectory() as temp,patch('gui.HERE',Path(temp)),patch('gui.subprocess.Popen') as spawn:
            app=App();identifier='0123456789ab';root=app.folder('test');(root/'candidates').mkdir(parents=True)
            candidate=root/'candidates'/(identifier+'.json');candidate.write_text(json.dumps(dict(id=identifier,bodies=['Earth','Saturn'])))
            (root/'request.json').write_text(json.dumps(dict(target='Saturn')))
            baseline=root/'exports'/identifier;baseline.mkdir(parents=True)
            for name in ('trajectory.xyzv','burns.csv'):(baseline/name).touch()
            (baseline/'integration_report.json').write_text(json.dumps(dict(numerical_validation_passed=True,source_candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest())))
            spawn.return_value.poll.return_value=None
            result=app.target_moon('test',identifier,'606','approach',500)
            request=json.loads((root/'moon_targets'/identifier/result['branch']/'request.json').read_text())
            self.assertEqual(request['baseline_folder'],str(baseline));self.assertEqual(request['options']['altitude'],500)
            with self.assertRaises(ValueError):app.target_moon('test',identifier,'606')
            app.close_moon_jobs()
            self.assertTrue((root/'moon_targets'/identifier/result['branch']/'stop.request').exists())

if __name__=='__main__':unittest.main()
