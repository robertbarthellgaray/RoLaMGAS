"""Entry rotation, thermodynamic provenance, force direction and energy checks."""
import bootstrap
from pathlib import Path
import tempfile,unittest,json,csv
import numpy as np
from titan_entry import Atmosphere,forces,integrate,RADIUS,MU,OMEGA,incoming,append_prefix
from moon_targets import titan_body_axes,titan_target_normal
from tools.prepare_titan_atmosphere import parse_profile,MOLAR_MASS,R_GAS
ROOT=Path(__file__).resolve().parent

class TitanEntryTests(unittest.TestCase):
    def test_bundled_column_uses_archived_density_products(self):
        metadata=json.loads((ROOT/'model_assets/titan/hasi_reference.json').read_text())
        self.assertEqual(metadata['rows'],2727);self.assertEqual(metadata['eos_fallback_rows'],0)
        self.assertTrue(any('/ACC/HASI_L4_ACCE_DENSITY.TAB' in item['url'] for item in metadata['sources']))
        with (ROOT/'model_assets/titan/hasi_reference.csv').open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
        self.assertEqual(sum(row['source']=='HASI_ACC_density' for row in rows),911)
        self.assertEqual(sum(row['source']=='HASI_descent_density' for row in rows),1816)
    def test_export_join_translates_with_jpl_and_refuses_state_resets(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);epoch=2464300.;moon=np.array([1e9,2e8,0.,1.,7.,0.]);local=np.array([4000.,0.,0.,-7.,2.,0.])
            entry=np.array([np.r_[epoch,local],np.r_[epoch+1/86400,local+[-7.,2.,0.,0.,0.,0.]]]);source=np.array([np.r_[epoch-1/86400,local+moon+[7.,-2.,0.,0.,0.,0.]],np.r_[epoch,local+moon]])
            prefix=folder/'prefix.xyzv';np.savetxt(prefix,source,fmt='%.12f')
            with patch('ephemeris.Ephemerides') as ep:
                ep.return_value.state.return_value=moon
                report=append_prefix(prefix,entry,folder,folder);self.assertEqual(report['rows'],3);self.assertLess(report['position_join_error_km'],1e-6)
                source[-1,1]+=100;np.savetxt(prefix,source,fmt='%.12f')
                with self.assertRaisesRegex(ValueError,'mismatch'):append_prefix(prefix,entry,folder,folder)
            source[0,1]=float('nan');np.savetxt(prefix,source)
            with self.assertRaisesRegex(ValueError,'finite'):append_prefix(prefix,entry,folder,folder)

    def test_missing_archived_entry_density_is_explicitly_derived_not_zero(self):
        with self.assertRaises(ValueError):parse_profile(b'0;100000;10;150;\n','entry')
        rows,count=parse_profile(b'0;100000;10;150;\n','entry',allow_derived=True)
        self.assertEqual(count,1);self.assertAlmostEqual(rows[0][1],10*MOLAR_MASS/(R_GAS*150))
        self.assertIn('EOS',rows[0][4])
        rows,count=parse_profile(b'0;100000;10;150;\n','entry',{100000.:.001})
        self.assertEqual(count,0);self.assertEqual(rows[0][1],.001);self.assertEqual(rows[0][4],'HASI_ACC_density')
        with self.assertRaises(ValueError):parse_profile(b'0;100000;10;150;\n','descent')

    def test_force_uses_air_velocity_and_dissipates_air_relative_energy(self):
        atmosphere=Atmosphere(ROOT/'model_assets/titan/hasi_reference.csv');pole=titan_body_axes(2464300.)[2]
        position=(RADIUS+200000)*titan_target_normal(2464300.,4.,162.5)
        corot=np.cross(OMEGA*pole,position);velocity=corot+np.array([1000.,2000.,-1000.])
        aero,d=forces(np.r_[position,velocity],atmosphere,pole,70.)
        self.assertLess(aero@(velocity-corot),0.)
        zero,_=forces(np.r_[position,corot],atmosphere,pole,70.);np.testing.assert_allclose(zero,0,atol=1e-16)
        self.assertGreater(d['dynamic_pressure_pa'],0.)

    def test_public_reference_reaches_handoff_and_preserves_energy_work_balance(self):
        epoch=2464300.;normal=titan_target_normal(epoch,0,0);axes=titan_body_axes(epoch);position=(RADIUS+1270000)*normal
        gamma=np.radians(-48.);velocity=7300*(np.sin(gamma)*normal+np.cos(gamma)*axes[1])+np.cross(OMEGA*axes[2],position)
        initial=np.r_[position,velocity]/1000
        atmosphere=Atmosphere(ROOT/'model_assets/titan/hasi_reference.csv')
        report,times,states,diagnostics=integrate(epoch,initial,atmosphere)
        self.assertTrue(report['completed']);self.assertEqual(report['outcome'],'mach_1_5_handoff')
        self.assertAlmostEqual(diagnostics[-1]['mach'],1.5,places=7)
        self.assertGreater(diagnostics[-1]['altitude_m'],50000);self.assertLess(diagnostics[-1]['altitude_m'],250000)
        self.assertLess(abs(report['energy_work_balance_error_j_kg']),.1)
        np.testing.assert_allclose(states[0],initial,atol=1e-12)
        self.assertTrue(np.all(np.diff(times)>0));self.assertGreater(report['peak_dynamic_pressure']['dynamic_pressure_pa'],1000.)

    def test_unphysical_profiles_and_wrong_frame_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'bad.csv';path.write_text('altitude_m,density_kg_m3,temperature_k,pressure_pa\n0,0,90,100\n1,-1,90,100\n2,1,90,100\n')
            with self.assertRaises(ValueError):Atmosphere(path)
            state=Path(temp)/'state.json';state.write_text(json.dumps(dict(body='Titan',frame='body-fixed',epoch_jd_tdb=2464300,position_km=[4000,0,0],velocity_kms=[-7,0,0])))
            with self.assertRaises(ValueError):incoming(state)

if __name__=='__main__':unittest.main()
