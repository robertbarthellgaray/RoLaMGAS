import bootstrap  # noqa: F401
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
import zipfile
from celestia_package import HERE,MODELS,build_package,choose_model
from ephemeris import AU


class CelestiaPackageTests(unittest.TestCase):
    def test_automatic_panels_for_jupiter(self):
        self.assertEqual(choose_model({'bodies':['Earth','Jupiter']},{'target':'Jupiter'},5.4)[0],'Panels')

    def test_automatic_rtg_for_outer_and_dwarf_targets(self):
        self.assertEqual(choose_model({'bodies':['Earth','Saturn']},{'target':'Saturn'},9.5)[0],'RTG')
        self.assertEqual(choose_model({'bodies':['Earth','1 Ceres']},{'target_object':{'name':'1 Ceres','semimajor_axis_au':2.77}},2.8)[0],'RTG')
        self.assertEqual(choose_model({'bodies':['Earth','Target']},{'target_object':{'name':'2026 ED138','semimajor_axis_au':42.9}},43)[0],'RTG')

    def test_explicit_model_override(self):
        self.assertEqual(choose_model({'bodies':['Earth','Neptune']},{'target':'Neptune'},30,'Panels')[0],'Panels')

    def fixture(self,folder):
        p=Path(folder)
        report=dict(numerical_validation_passed=True,no_sample_bracketed_planet_or_sun_impacts=True,
                    start_jd_tdb=2462502.5,end_jd_tdb=2464000.5,patch_join_delta_v_kms=.2,
                    passes_original_onboard_budget=True)
        (p/'integration_report.json').write_text(json.dumps(report))
        (p/'trajectory.xyzv').write_text('2462502.5 149597870.7 0 0 0 30 0\n2464000.5 777908927.64 0 0 0 13 0\n')
        (p/'trajectory.csv').write_text(f'julian_date_tdb,x_km,y_km,z_km,vx_kms,vy_kms,vz_kms\n2462502.5,{AU},0,0,0,30,0\n2464000.5,{5.2*AU},0,0,0,13,0\n')
        return dict(id='0123456789ab',bodies=['Earth','Jupiter'],launch_date='2030-01-01 TDB',arrival_date='2034-02-07 TDB')

    def test_both_packages_include_exact_model_and_referenced_trajectory(self):
        with tempfile.TemporaryDirectory() as folder:
            q=self.fixture(folder)
            for model in ('Panels','RTG'):
                result=build_package(folder,q,{'target':'Jupiter'},model)
                filename=MODELS[model]
                source=next(p for p in (HERE.parent/filename,HERE/'model_assets'/filename) if p.is_file())
                with zipfile.ZipFile(Path(folder)/result['filename']) as archive:
                    self.assertIsNone(archive.testzip())
                    names=archive.namelist()
                    self.assertTrue(all(not name.startswith('/') and '..' not in Path(name).parts for name in names))
                    mesh=next(name for name in names if name.endswith('/models/'+filename))
                    self.assertEqual(hashlib.sha256(archive.read(mesh)).hexdigest(),hashlib.sha256(source.read_bytes()).hexdigest())
                    ssc=archive.read(next(n for n in names if n.endswith('.ssc'))).decode()
                    self.assertIn('NormalizeMesh true',ssc)
                    self.assertIn('Mesh "'+filename+'"',ssc)
                    self.assertTrue(any(n.endswith('/data/trajectory_0123456789ab.xyzv') for n in names))

    def test_impact_report_cannot_be_silently_packaged(self):
        with tempfile.TemporaryDirectory() as folder:
            q=self.fixture(folder);p=Path(folder)/'integration_report.json';r=json.loads(p.read_text())
            r['no_sample_bracketed_planet_or_sun_impacts']=False;p.write_text(json.dumps(r))
            with self.assertRaises(ValueError):build_package(folder,q,{'target':'Jupiter'})

    def test_near_miss_and_over_budget_package_retains_violations(self):
        with tempfile.TemporaryDirectory() as folder:
            q=self.fixture(folder);q['status']='near_miss_not_accepted'
            p=Path(folder)/'integration_report.json';r=json.loads(p.read_text())
            r.update(candidate_passes_requested_limits=False,passes_original_onboard_budget=False,
                     requirement_violations=['Arrival speed exceeds requested limit'])
            p.write_text(json.dumps(r))
            result=build_package(folder,q,{'target':'Jupiter'})
            self.assertFalse(result['candidate_passes_requested_limits'])
            self.assertFalse(result['passes_original_onboard_budget'])
            with zipfile.ZipFile(Path(folder)/result['filename']) as archive:
                manifest=json.loads(archive.read(next(n for n in archive.namelist() if n.endswith('/package_manifest.json'))))
                self.assertEqual(manifest['requirement_violations'],r['requirement_violations'])


if __name__=='__main__':unittest.main()
