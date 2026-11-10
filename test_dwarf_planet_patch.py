"""The Celestia override must preserve frames, identity, spin and year bounds."""
from pathlib import Path
import json,tempfile,unittest,zipfile
from unittest.mock import patch
import numpy as np
import dwarf_planet_patch as dwarf
from celestia_package import build_package
import test_celestia_package as package_tests
from ephemeris import jd,DAY

class CachedVectors:
    def __init__(self,*args,**kwargs):self.manifest={'1 Ceres':{'source':'synthetic test vectors'}}
    def state(self,name,t):return np.array([4e8+(t-jd('2034-01-01'))*DAY,2e8,3e6,1.,0.,0.])

class DwarfPatchTests(unittest.TestCase):
    def objects(self):return json.loads(dwarf.ASSET.read_text(encoding='utf-8'))['objects']
    def config(self):return dict(target='1 Ceres',target_object=dict(name='1 Ceres',id='20000001',designation='1',command='1;',kind='small_body'))
    def test_barycenter_and_physical_pluto_are_distinct(self):
        bary=dict(target_object=dict(name='Pluto Barycenter',id='9',command='9'))
        physical=dict(target_object=dict(name='Pluto',id='999',command='999'))
        self.assertEqual(dwarf.select_template(bary,self.objects())[0]['name'],'Pluto-Charon')
        self.assertEqual(dwarf.select_template(physical,self.objects())[0]['name'],'Pluto')
        self.assertIsNone(dwarf.select_template(dict(target='Mars'),self.objects())[0])
    def test_parser_ignores_comment_braces_and_preserves_implicit_spin_period(self):
        text='''ReferencePoint "Pair" "Sol" { EllipticalOrbit { Period 200 SemiMajorAxis 40 } }
        "Pluto:134340 Pluto" "Sol" {
          Class "dwarfplanet" # } a false brace
          Texture "a{b}.png"
          OrbitFrame { EclipticJ2000 { Center "Sol/Pair" } }
          EllipticalOrbit { Period 6.387221 SemiMajorAxis 2130.734 }
          BodyFrame { EclipticJ2000 {} }
          UniformRotation { Inclination 112.88 }
        }'''
        row=dwarf.catalog_from_ssc(text)[1]
        self.assertIn('153.293304',row['properties']['UniformRotation'])
        self.assertNotIn('Texture',row['properties'])
        self.assertIn('Sol/Pair',row['properties']['OrbitFrame'])
    def test_package_adds_three_phase_timeline_and_exact_states(self):
        with tempfile.TemporaryDirectory() as folder:
            q=package_tests.CelestiaPackageTests().fixture(folder)
            q.update(bodies=['Earth','1 Ceres'],dates_jd_tdb=[jd('2033-01-01'),jd('2034-02-07T12:34:56')])
            with patch.object(dwarf,'Ephemerides',CachedVectors),patch.object(dwarf,'fetch',side_effect=AssertionError('Cached data must stay offline')):
                result=build_package(folder,q,self.config(),patch_dwarf_planet=True)
            p=result['dwarf_planet_patch'];self.assertEqual(p['start_date'],'2034-01-01');self.assertEqual(p['end_date'],'2035-01-01')
            with zipfile.ZipFile(Path(folder)/result['filename']) as z:
                ssc=z.read(next(n for n in z.namelist() if n.endswith('/jpl_dwarf_planet_patch.ssc'))).decode()
                self.assertIn('Modify "Ceres" "Sol"',ssc)
                self.assertEqual(ssc.count('EllipticalOrbit'),2)
                self.assertEqual(ssc.count('UniformRotation'),3)
                self.assertIn('Center "Sol"',ssc)
                self.assertIn('Celestia_orbit_LICENSE.txt',' '.join(z.namelist()))
                name=next(n for n in z.namelist() if '/data/jpl_' in n)
                rows=np.array([[float(v) for v in line.split()] for line in z.read(name).decode().splitlines()])
                self.assertTrue(np.all(np.diff(rows[:,0])>0))
                target=rows[np.argmin(abs(rows[:,0]-q['dates_jd_tdb'][-1]))]
                self.assertAlmostEqual(target[0],q['dates_jd_tdb'][-1],places=9)
                np.testing.assert_allclose(target[1:],CachedVectors().state('1 Ceres',target[0]),atol=1e-6)
            # Disabling the option returns an addon with no stale override.
            plain=build_package(folder,q,self.config(),patch_dwarf_planet=False)
            with zipfile.ZipFile(Path(folder)/plain['filename']) as z:self.assertFalse(any('jpl_dwarf' in n for n in z.namelist()))
    def test_failed_jpl_request_never_yields_a_successful_package(self):
        with tempfile.TemporaryDirectory() as folder:
            q=package_tests.CelestiaPackageTests().fixture(folder);q.update(bodies=['Earth','1 Ceres'],dates_jd_tdb=[jd('2033-01-01'),jd('2034-02-07')])
            with patch.object(dwarf,'Ephemerides',side_effect=ValueError('missing coverage')),patch.object(dwarf,'fetch',side_effect=OSError('offline')):
                with self.assertRaisesRegex(OSError,'offline'):build_package(folder,q,self.config(),patch_dwarf_planet=True)
            self.assertFalse(list(Path(folder).glob('*_JPL.zip')))

if __name__=='__main__':unittest.main()
