import bootstrap
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from ephemeris import Ephemerides,DAY,JD0,parse_horizons
from horizons_targets import resolve,register_target,identity,pluto_identity
from moon_targets import target_options,parent_parameters,validate_options,named_moon
from planet_moon_patch import templates,source_tables,validate_patch_step
from moon_arrival import MoonSystem,local_moon,propagate

class TargetPatchTests(unittest.TestCase):
    def test_numbered_pluto_is_the_physical_center_and_barycenter_remains_distinct(self):
        with patch('horizons_targets.request_json',side_effect=AssertionError('Known alias should resolve offline')):
            for query in ('134340 Pluto','134340 Pluto (1930 BM)','134340','SPK=999','SPK=20134340','Pluto'):
                desc=resolve(query);self.assertEqual((desc['id'],desc['command']),('999','999'))
        register_target(dict(name='134340 Pluto (1930 BM)',id='20134340',designation='134340',command='134340;',kind='small_body'))
        text=(Path(__file__).parent/'test_fixtures/pluto_numbered_horizons.txt').read_text(encoding='utf-8')
        times,states=parse_horizons(text,'134340 Pluto (1930 BM)')
        self.assertEqual(len(times),5);self.assertTrue(np.isfinite(states).all())
        register_target(dict(name='Pluto Barycenter',id='9',command='9',kind='horizons_object'))
        self.assertEqual(identity('Pluto Barycenter')['id'],'9')

    def test_moon_lookup_confirms_pluto_parent_and_preserves_portable_search_intent(self):
        from gui import App
        from mission_search import normalize
        with tempfile.TemporaryDirectory() as folder,patch('gui.HERE',Path(folder)),patch('gui.resolve',side_effect=AssertionError('Known moon is offline')):
            app=App();moon=app.lookup('Charon','2030-01-01')
            self.assertEqual(moon['parent_body'],'Pluto');parent=app.targets['pluto']
            config=normalize(dict(target='Pluto',target_object=parent,sequences=['EJX'],moon_target=dict(parent='Pluto',moon_id='901')))
            self.assertEqual(config['moon_target']['moon_name'],'Charon')
            self.assertEqual(config['target_object']['id'],'999')

    def test_windows_degree_sign_and_missing_license_header_do_not_break_planet_moon_catalog(self):
        text='''# Old catalog: 90° north\n"Neptune" "Sol" { Class "planet" CustomOrbit "neptune" UniformRotation { Period 16 } }\n"Triton" "Sol/Neptune" { Class "moon" EllipticalOrbit { Period 5.87 SemiMajorAxis 354759 } UniformRotation { } }'''
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'Celestia/data';path.mkdir(parents=True)
            (path/'solarsys.ssc').write_bytes(text.encode('cp1252'))
            with patch.dict('os.environ',{'ProgramFiles':folder}):result=templates()
        self.assertEqual({r['name'] for r in result['objects']},{'Neptune','Triton'})
        self.assertEqual(result['catalogs'][0]['encoding'],'windows-1252')
        self.assertEqual(result['catalogs'][0]['license'],'not specified in source catalog')

    def test_saved_extensions_and_invalid_sources_have_clear_provenance_handling(self):
        a=dict(raw_file='original.txt');b=dict(raw_file='later.txt')
        self.assertEqual(source_tables(dict(original_tables=[a],extension_tables=[b])),[a,b])
        with self.assertRaisesRegex(ValueError,'provenance'):source_tables([None])
        for value in (0,-1,31,float('nan')):
            with self.assertRaises(ValueError):validate_patch_step(value)

    def test_only_jd_roundoff_is_clamped_and_actual_extrapolation_names_the_body(self):
        ep=Ephemerides.__new__(Ephemerides);start=1e9;stop=start+10
        curve=CubicHermiteSpline([start,stop],[[0,0,0],[10,0,0]],[[1,0,0],[1,0,0]],extrapolate=False)
        ep.splines={'Triton':curve}
        np.testing.assert_allclose(ep.state('Triton',JD0+(stop+.0001)/DAY)[:3],[10,0,0],atol=.0002)
        with self.assertRaisesRegex(ValueError,'Triton.*cached coverage'):ep.state('Triton',JD0+(stop+10)/DAY)

    def test_pluto_has_five_trusted_satellite_models_and_small_gm_limits_are_not_invented(self):
        self.assertEqual({m['name'] for m in target_options('134340 Pluto (1930 BM)')},{'Charon','Nix','Hydra','Styx','Kerberos'})
        self.assertEqual(parent_parameters('Pluto')[1],869.3)
        for moon in target_options('Pluto'):
            self.assertEqual(validate_options('Pluto',moon['id'],'approach',100)['parent'],'Pluto')
            self.assertEqual(named_moon(moon['name'])['parent_body'],'Pluto')
            if moon['name'] in ('Styx','Kerberos'):
                self.assertEqual(moon['gm'],0);self.assertIn('Massless',moon['gm_note'])

    def test_charon_perturbation_and_analytic_velocity_sensitivities_are_used(self):
        parent=lambda date:np.zeros(6)
        satellite=lambda date:np.array([60000.,20000,0,0,0,0])
        charon=lambda date:np.array([19600.,0,0,0,0,0])
        body=dict(name='Charon',gm=106.1,radius_km=606.)
        system=MoonSystem('Pluto','Hydra',869.3,1188.3,.002,18.5,perturbers=((body,charon),))
        moon=local_moon(satellite,parent,2451545.,system)
        y=np.array([100000.,-10000.,5000.,-2.,1.,.1]);seconds=3000.
        fit=propagate(y,seconds,moon,system=system,variational=True)
        unperturbed=propagate(y,seconds,lambda t:satellite(0)[:3],system=MoonSystem('Pluto','Hydra',869.3,1188.3,.002,18.5))
        self.assertGreater(np.linalg.norm(fit.y[:3,-1]-unperturbed.y[:3,-1]),.01)
        columns=[];eps=1e-5
        for axis in np.eye(3):
            d=np.r_[np.zeros(3),axis*eps]
            columns.append((propagate(y+d,seconds,moon,system=system).y[:3,-1]-propagate(y-d,seconds,moon,system=system).y[:3,-1])/(2*eps))
        np.testing.assert_allclose(fit.y[6:,-1].reshape(6,3)[:3],np.column_stack(columns),rtol=2e-6,atol=.002)

if __name__=='__main__':unittest.main()
