"""Moon continuation preserves source states, costs and selected export routing."""
import bootstrap  # noqa: F401
import hashlib,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from ephemeris import AU,DAY,JD0,atomic_json,BODIES
from moon_continuation import extend,continuation_path
import test_moon_export as existing
from moon_targeting import write_states


class MoonContinuationTests(unittest.TestCase):
    def test_continuous_unpowered_extension_routed_into_package_and_zero_restores_original(self):
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
            app,root,source,ident,branch=existing.MoonExportTests().fixture(folder)
            epoch=2462867.5;moon_radius=670000.;n=np.sqrt(BODIES['Jupiter'][1]/moon_radius**3)
            t=np.arange(-1,26,.005)*DAY
            parent=np.tile([5.2*AU,0,0,0,0,0],(len(t),1))
            rel=np.c_[moon_radius*np.cos(n*t),moon_radius*np.sin(n*t),t*0,
                -moon_radius*n*np.sin(n*t),moon_radius*n*np.cos(n*t),t*0]
            curves={b:CubicHermiteSpline((epoch-JD0)*DAY+t,states[:,:3],states[:,3:],extrapolate=False)
                for b,states in [('Jupiter',parent),('Europa',parent+rel)]}
            initial=np.array([5.2*AU+moon_radius,1900.,0,30,n*moon_radius,0])
            rows=np.array([np.r_[epoch-1,initial-np.r_[initial[3:]*DAY,np.zeros(3)]],np.r_[epoch,initial]])
            write_states(source/'trajectory.xyzv',rows);write_states(source/'trajectory.csv',rows,True)
            report=json.loads((source/'moon_report.json').read_text());report.update(target_epoch_jd_tdb=epoch,target_mode='approach',
                ephemeris_sources={'Jupiter':[],'Europa':[]},force_segments=[],force_model='Test source',
                trajectory_sha256=hashlib.sha256((source/'trajectory.xyzv').read_bytes()).hexdigest())
            atomic_json(source/'moon_report.json',report)
            prefix=(source/'trajectory.xyzv').read_bytes();burns=(source/'burns.csv').read_bytes()
            app.select_moon_export('saved',ident,branch)
            with patch('gui.subprocess.Popen',return_value=SimpleNamespace(poll=lambda:None)) as launch:
                response=app.integrate('saved',ident,post_flyby_months=.5)
                self.assertTrue(response['started']);self.assertIn('moon_continuation.py',str(launch.call_args))
            self.assertEqual(app.export_status('saved',ident)['state'],'running')
            output=continuation_path(source,.5)
            with patch('moon_continuation.load_vectors',side_effect=lambda cache,body,*args:(curves[body],[])):
                result=extend(source,output,app.cache,.5,lambda message:None)
            atomic_json(output/'integration_status.json',dict(state='finished'))
            self.assertEqual((source/'trajectory.xyzv').read_bytes(),prefix)
            self.assertTrue((output/'trajectory.xyzv').read_bytes().startswith(prefix))
            self.assertEqual((output/'burns.csv').read_bytes(),burns)
            self.assertEqual(result['continuation_added_burn_kms'],0.)
            self.assertLess(result['continuation_join_position_error_km'],1e-6)
            self.assertLess(result['continuation_join_velocity_error_kms'],1e-10)
            self.assertAlmostEqual(result['end_jd_tdb']-epoch,.5*365.25/12,places=8)
            states=np.loadtxt(output/'trajectory.xyzv');self.assertTrue(np.all(np.diff(states[:,0])>0))
            self.assertTrue(np.isfinite(states).all())
            status=app.export_status('saved',ident)
            self.assertEqual(status['report']['post_flyby_months'],.5)
            self.assertIn('/continuations/',status['file_base'])
            with patch('celestia_package.build_package',return_value={}) as package:
                app.package('saved',ident,post_flyby_months=.5)
                self.assertEqual(package.call_args.args[0],output)
                self.assertEqual(package.call_args.kwargs['moon_branch'],branch)
            app.integrate('saved',ident,post_flyby_months=0)
            self.assertEqual(app.export_status('saved',ident)['report'].get('post_flyby_months',0),0)

    def test_entry_and_impact_cannot_continue_through_surface(self):
        for mode in ('impact','entry'):
            with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)):
                app,root,out,ident,branch=existing.MoonExportTests().fixture(folder,mode)
                if mode=='entry':
                    report=json.loads((out/'moon_report.json').read_text());report['achieved_altitude_km']=1270.
                    atomic_json(out/'moon_report.json',report)
                app.select_moon_export('saved',ident,branch)
                with self.assertRaisesRegex(ValueError,'closest-approach'):app.integrate('saved',ident,post_flyby_months=600)

    def test_compact_patch_retains_encounter_with_checked_position_and_velocity(self):
        from planet_moon_patch import compact_vectors
        period=5.877*DAY;n=2*np.pi/period;t=np.arange(0,12*DAY+1,120.)
        dates=JD0+t/DAY;t=(dates-JD0)*DAY
        r=354759.;states=np.c_[r*np.cos(n*t),r*np.sin(n*t),t*0,-r*n*np.sin(n*t),r*n*np.cos(n*t),t*0]
        encounter=dates[len(dates)//2]
        compact,values,report=compact_vectors(dates,states,encounter)
        self.assertLess(len(compact),len(dates)/10);self.assertIn(encounter,compact)
        truth=CubicHermiteSpline(t,states[:,:3],states[:,3:])
        curve=CubicHermiteSpline((compact-JD0)*DAY,values[:,:3],values[:,3:])
        check=np.linspace(0,t[-1],30001)
        self.assertLess(np.max(np.linalg.norm(curve(check)-truth(check),axis=1)),.05)
        self.assertLess(np.max(np.linalg.norm(curve(check,1)-truth(check,1),axis=1)),1e-6)

if __name__=='__main__':unittest.main()
