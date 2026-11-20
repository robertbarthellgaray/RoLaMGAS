"""Selecting a moon simulation must change the bytes in the Celestia package."""
import bootstrap  # noqa: F401
import csv,hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from ephemeris import DAY,JD0,atomic_json
from gui import App


class MoonExportTests(unittest.TestCase):
    def test_rounding_at_fractional_jd_table_boundary_never_extrapolates(self):
        from scipy.interpolate import CubicHermiteSpline
        from planet_moon_patch import spline_states,validate_patch_days
        # Actual failing Ganymede boundary: JD roundtrip overshoots by 18 us.
        end=(2465647.5-JD0)*DAY-3000
        curve=CubicHermiteSpline([end-1,end],[[0,0,0],[1,2,3]],[[1,2,3],[1,2,3]],extrapolate=False)
        roundtrip=((JD0+end/DAY)-JD0)*DAY
        self.assertGreater(roundtrip,end)
        self.assertTrue(np.all(np.isfinite(spline_states(curve,[roundtrip]))))
        with self.assertRaisesRegex(ValueError,'coverage'):spline_states(curve,[end+1])
        for value in (0,-1,float('inf'),float('nan'),4000):
            with self.assertRaises(ValueError):validate_patch_days(value)

    def test_centered_duration_enforces_one_orbit_and_extends_without_replacing_original_knots(self):
        from scipy.interpolate import CubicHermiteSpline
        from types import SimpleNamespace
        from planet_moon_patch import create_patches
        from ephemeris import BODIES
        mu=BODIES['Jupiter'][1]+9887.83275;radius=1070400.;omega=np.sqrt(mu/radius**3)
        period=2*np.pi/omega/DAY;epoch=2465644.4519698867;zero=(epoch-JD0)*DAY
        def physical(times,body):
            dt=times-zero;parent=np.c_[7e8+dt*10,np.zeros((len(times),2)),np.full(len(times),10.),np.zeros((len(times),2))]
            rel=np.c_[radius*np.cos(omega*dt),radius*np.sin(omega*dt),np.zeros(len(times)),-radius*omega*np.sin(omega*dt),radius*omega*np.cos(omega*dt),np.zeros(len(times))]
            return parent if body=='Jupiter' else parent+rel
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cache=root/'cache';cache.mkdir();sources={};original={}
            for body in ('Jupiter','Ganymede'):
                times=zero+np.arange(-10,2.6,.25)*DAY;values=physical(times,body)
                path=cache/(body+'.npz');np.savez(path,times=times,states=values)
                sources[body]=[dict(raw_file=body+'.txt',npz_sha256=hashlib.sha256(path.read_bytes()).hexdigest())]
                original[body]=CubicHermiteSpline(times,values[:,:3],values[:,3:])
            def extended(cache,bodies,start,end,*args,**kwargs):
                if not downloaded:raise ValueError('No extended coverage')
                times=zero+np.arange(-40,40.01,1/24)*DAY
                return SimpleNamespace(splines={b:CubicHermiteSpline(times,physical(times,b)[:,:3],physical(times,b)[:,3:]) for b in bodies},manifest={b:[] for b in bodies})
            downloaded=[]
            report=dict(parent_body='Jupiter',moon_id='503',target_epoch_jd_tdb=epoch,end_jd_tdb=epoch,ephemeris_sources=sources)
            with patch('planet_moon_patch.Ephemerides',side_effect=extended),patch('planet_moon_patch.fetch',side_effect=lambda *a:downloaded.append(a)):
                result=create_patches(root,dict(cache=str(cache)),report,True,True,patch_days=1)
            self.assertTrue(downloaded);self.assertAlmostEqual(result['effective_duration_days'],period,places=10)
            p=result['patches'][0];self.assertAlmostEqual((p['start_jd_tdb']+p['end_jd_tdb'])/2,epoch,places=9)
            self.assertAlmostEqual(epoch-p['start_jd_tdb'],period/2,places=8)
            rows=np.loadtxt(root/'data/jpl_ganymede.xyzv');self.assertTrue(np.all(np.isfinite(rows)))
            seconds=(rows[:,0]-JD0)*DAY;inside=(seconds>=original['Ganymede'].x[0])&(seconds<=original['Ganymede'].x[-1])
            expected=original['Ganymede'](seconds[inside])-original['Jupiter'](seconds[inside])
            np.testing.assert_allclose(rows[inside,1:4],expected,atol=1e-6)
            # A longer manual window remains centered and is not silently cut.
            with patch('planet_moon_patch.Ephemerides',side_effect=extended),patch('planet_moon_patch.fetch',side_effect=AssertionError('Reuse extended cache')):
                manual=create_patches(root,dict(cache=str(cache)),report,True,True,patch_days=30)
            self.assertEqual(manual['effective_duration_days'],30)
            self.assertAlmostEqual(manual['patches'][0]['end_jd_tdb']-manual['patches'][0]['start_jd_tdb'],30)

    def fixture(self,folder,mode='approach'):
        app=App();root=app.folder('saved');candidate='0123456789ab';branch='1123456789ab'
        q=dict(id=candidate,bodies=['Earth','Jupiter'],launch_date='2030-01-01',arrival_date='2031-01-01')
        atomic_json(root/'candidates'/f'{candidate}.json',q)
        checksum=hashlib.sha256((root/'candidates'/f'{candidate}.json').read_bytes()).hexdigest()
        atomic_json(root/'request.json',dict(target='Jupiter',cache=str(app.cache)))
        out=root/'moon_targets'/candidate/branch;out.mkdir(parents=True)
        atomic_json(out/'status.json',dict(state='finished'))
        atomic_json(out/'source_export/integration_report.json',dict(source_candidate_sha256=checksum,no_sample_bracketed_planet_or_sun_impacts=True))
        atomic_json(out/'moon_report.json',dict(source_candidate_id=candidate,parent_body='Jupiter',moon_body='Europa',moon_id='502',
            target_mode=mode,achieved_altitude_km=100 if mode=='approach' else -.001,
            numerical_validation_passed=True,independent_sun_and_parent_moon_propagation_passed=True,
            minimum_sampled_parent_altitude_km=500000,start_jd_tdb=2462502.5,end_jd_tdb=2462867.5,
            passes_original_onboard_budget=True,added_correction_delta_v_kms=.03))
        (out/'trajectory.xyzv').write_text('2462502.5 149597870 0 0 0 30 0\n2462867.5 700000000 12345 100 1 10 2\n')
        (out/'trajectory.csv').write_text('julian_date_tdb,x_km,y_km,z_km,vx_kms,vy_kms,vz_kms\n2462502.5,149597870,0,0,0,30,0\n2462867.5,700000000,12345,100,1,10,2\n')
        (out/'burns.csv').write_text('kind,magnitude_kms\nfinite_patch_junction,0.002\nMoon targeting cruise DSM,0.03\n')
        return app,root,out,candidate,branch

    def test_select_package_exact_branch_and_switch_back_without_integration(self):
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
            app,root,out,ident,branch=self.fixture(folder)
            result=app.select_moon_export('saved',ident,branch)
            self.assertEqual(result['export_kind'],'moon')
            with patch.object(app,'integrate',side_effect=AssertionError('Moon branch must never be reintegrated as a planet arrival')):
                result=app.package('saved',ident)
            self.assertEqual(result['moon_branch'],branch)
            self.assertEqual(result['additional_patch_burns_kms'],.002)
            with zipfile.ZipFile(out/result['filename']) as archive:
                xyzv=next(n for n in archive.namelist() if n.endswith('/data/trajectory_'+ident+'.xyzv'))
                self.assertEqual(archive.read(xyzv),(out/'trajectory.xyzv').read_bytes())
                self.assertTrue(any(n.endswith('/reports/moon_report.json') for n in archive.namelist()))
            # Selection persists across reopening an application and does not
            # overwrite the parent trajectory folder or launch a worker.
            self.assertEqual(App().export_status('saved',ident)['branch'],branch)
            self.assertFalse((root/'exports'/ident).exists())
            self.assertEqual(app.select_moon_export('saved',ident)['state'],'none')

    def test_numbered_small_body_alias_selects_its_own_branch_without_rewriting_candidate(self):
        for full_name,parent in [('90482 Orcus (2004 DW)','Orcus'),('Orcus (primary body)','Orcus'),('136199 Eris (2003 UB313)','Eris'),('136199 Eris','Eris'),('134340 Pluto (1930 BM)','Pluto'),('134340 Pluto','Pluto'),('Pluto','Pluto')]:
            with self.subTest(parent=parent),tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
                app,run,out,ident,branch=self.fixture(folder)
                candidate=run/'candidates'/f'{ident}.json'
                q=json.loads(candidate.read_text());q['bodies'][-1]=full_name;atomic_json(candidate,q)
                digest=hashlib.sha256(candidate.read_bytes()).hexdigest()
                baseline=out/'source_export/integration_report.json';b=json.loads(baseline.read_text());b['source_candidate_sha256']=digest;atomic_json(baseline,b)
                report=out/'moon_report.json';r=json.loads(report.read_text());r['parent_body']=parent;atomic_json(report,r)
                selected=app.select_moon_export('saved',ident,branch)
                self.assertEqual(selected['export_kind'],'moon');self.assertEqual(selected['branch'],branch)
                self.assertEqual(hashlib.sha256(candidate.read_bytes()).hexdigest(),digest)
                # A stale candidate stays invalid even when its alias resolves.
                q['launch_date']='2030-01-02';atomic_json(candidate,q)
                with self.assertRaisesRegex(ValueError,'different candidate'):app.selected_moon_export('saved',ident)

    def test_every_catalogued_parent_full_name_can_select_its_own_branch(self):
        from moon_targets import CATALOG_SYSTEMS
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
            app,run,out,ident,branch=self.fixture(folder)
            candidate=run/'candidates'/f'{ident}.json'
            baseline=out/'source_export/integration_report.json';b=json.loads(baseline.read_text())
            report=out/'moon_report.json';r=json.loads(report.read_text());q=json.loads(candidate.read_text())
            for parent,system in CATALOG_SYSTEMS.items():
                with self.subTest(parent=parent):
                    q['bodies'][-1]=system.get('fullname') or parent;atomic_json(candidate,q)
                    b['source_candidate_sha256']=hashlib.sha256(candidate.read_bytes()).hexdigest();atomic_json(baseline,b)
                    r['parent_body']=parent;atomic_json(report,r)
                    self.assertEqual(app.select_moon_export('saved',ident,branch)['export_kind'],'moon')

    def test_reject_unfinished_stale_or_changed_branch(self):
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
            app,root,out,ident,branch=self.fixture(folder)
            with self.assertRaises(ValueError):app.select_moon_export('saved',ident,'../../bad')
            atomic_json(out/'status.json',dict(state='running'))
            with self.assertRaises(ValueError):app.select_moon_export('saved',ident,branch)
            atomic_json(out/'status.json',dict(state='finished'));app.select_moon_export('saved',ident,branch)
            with (out/'trajectory.xyzv').open('a') as f:f.write('# changed\n')
            with self.assertRaisesRegex(ValueError,'changed'):app.export_status('saved',ident)
            app.select_moon_export('saved',ident,branch)
            atomic_json(root/'candidates'/f'{ident}.json',dict(id=ident,bodies=['Earth','Saturn']))
            with self.assertRaisesRegex(ValueError,'different candidate'):app.package('saved',ident)

    def test_intentional_impact_allowed_but_unvalidated_arc_is_not(self):
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
            app,root,out,ident,branch=self.fixture(folder,'impact');app.select_moon_export('saved',ident,branch)
            self.assertEqual(app.package('saved',ident)['moon_target_mode'],'impact')
            report=json.loads((out/'moon_report.json').read_text());report['independent_sun_and_parent_moon_propagation_passed']=False
            atomic_json(out/'moon_report.json',report)
            with self.assertRaisesRegex(ValueError,'independent propagation'):app.export_status('saved',ident)

    def test_jpl_patch_subtracts_velocity_and_position_and_restores_stock_orbits(self):
        from planet_moon_patch import create_patches
        from scipy.interpolate import CubicHermiteSpline
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);epoch=2463165.;cache=root/'cache';cache.mkdir()
            times=(epoch-JD0)*DAY+np.arange(-20,21)*DAY
            parent=np.c_[np.full(len(times),7e8)+times*10,np.zeros((len(times),2)),np.full(len(times),10.),np.zeros((len(times),2))]
            rel=np.c_[np.full(len(times),670000.),(times-times[20])*2,np.full(len(times),100.),np.zeros(len(times)),np.full(len(times),2.),np.zeros(len(times))]
            sources={}
            for name,values in [('Jupiter',parent),('Europa',parent+rel)]:
                path=cache/(name+'.npz');np.savez(path,times=times,states=values)
                sources[name]=[dict(raw_file=name+'.txt',npz_sha256=hashlib.sha256(path.read_bytes()).hexdigest())]
            report=dict(parent_body='Jupiter',moon_id='502',target_epoch_jd_tdb=epoch,end_jd_tdb=epoch,ephemeris_sources=sources)
            with patch('planet_moon_patch.fetch',side_effect=AssertionError('Must use exact solver cache')):
                result=create_patches(root,dict(cache=str(cache)),report,True,True)
            self.assertEqual(len(result['patches']),2)
            rows=np.loadtxt(root/'data/jpl_europa.xyzv');expected=CubicHermiteSpline(times,rel[:,:3],rel[:,3:])((rows[:,0]-JD0)*DAY)
            np.testing.assert_allclose(rows[:,1:4],expected,atol=2e-6)
            np.testing.assert_allclose(rows[:,4:],np.tile([0,2,0],(len(rows),1)),atol=1e-12)
            text=(root/'jpl_europa_patch.ssc').read_text()
            self.assertIn('Modify "Europa" "Sol/Jupiter"',text);self.assertIn('Center "Sol/Jupiter"',text)
            self.assertEqual(text.count('CustomOrbit'),2);self.assertIn('Timeline',text)
            self.assertGreaterEqual(result['patches'][0]['end_jd_tdb']-result['patches'][0]['start_jd_tdb'],14)
            # Cache corruption must never silently substitute a different table.
            with (cache/'Europa.npz').open('ab') as f:f.write(b'bad')
            with self.assertRaisesRegex(ValueError,'checksum'):create_patches(root,dict(cache=str(cache)),report,True,True)


if __name__=='__main__':unittest.main()
