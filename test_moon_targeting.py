"""Moon branch safety, impulse accounting, and worker lifecycle contracts."""
import bootstrap  # noqa: F401
import csv,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import numpy as np
from ephemeris import DAY
from moon_targets import validate_options
from moon_targeting import finite_source,retained_burns,stitch_source
from moon_targets import titan_body_axes,titan_target_normal,titan_geography

class MoonTargetingTests(unittest.TestCase):
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
