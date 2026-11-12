"""Scientific export admission and custody of the original downloadable states."""
import json,tempfile,unittest,hashlib
from pathlib import Path
from unittest.mock import patch
import refresh_finite_downloads as refresh


class RefreshDownloadTests(unittest.TestCase):
    def report(self):
        return dict(numerical_validation_passed=True,no_sample_bracketed_planet_or_sun_impacts=True,
            passes_individual_burn_limits=True,passes_original_onboard_budget=True,candidate_passes_requested_limits=True,
            patch_join_delta_v_kms=.05,total_onboard_delta_v_kms=.6,exported_launch_c3_km2_s2=25.,rows=2,post_flyby_months=1.,
            finite_targeting=dict(changes=[dict(epoch_shift_days=-3.)]))

    def test_small_patch_number_alone_does_not_pass_publication(self):
        report=self.report();self.assertEqual(refresh.admitted(report,100),[])
        report['passes_individual_burn_limits']=False
        self.assertTrue(refresh.admitted(report,100))
        report=self.report();report['patch_join_delta_v_kms']=.101
        self.assertTrue(refresh.admitted(report,100))
        self.assertTrue(refresh.admitted(self.report(),100,dict(total_onboard_delta_v_kms=.5)))

    def test_updated_download_preserves_original_bytes_and_reconciles_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);downloads=root/'docs/downloads';downloads.mkdir(parents=True)
            cases=root/'docs/data/cases';cases.mkdir(parents=True);output=root/'review';output.mkdir()
            original=downloads/'original.xyzv';original.write_bytes(b'original archived states\n')
            old=dict(csv='downloads/original.csv',xyzv='downloads/original.xyzv')
            (cases/'example.json').write_text(json.dumps(dict(title='Example',trajectory_files=old)))
            for name in ['trajectory.csv','trajectory.xyzv','burns.csv','encounters.csv']:(output/name).write_bytes(b'numeric states\r\n')
            (output/'integration_report.json').write_text(json.dumps(self.report()))
            (output/'finite_targeting.json').write_text('{}')
            result=dict(id='example',selected_output=str(output),maximum_serialized_midpoint_error_km=.1)
            with patch.object(refresh,'ROOT',root):refresh.publish(result)
            self.assertEqual(original.read_bytes(),b'original archived states\n')
            case=json.loads((cases/'example.json').read_text());self.assertEqual(case['original_trajectory_files'],old)
            files=case['trajectory_files'];self.assertTrue(files['finite_radius']);self.assertEqual(files['maximum_epoch_shift_days'],3.)
            self.assertEqual(files['xyzv_sha256'],hashlib.sha256((root/'docs'/files['xyzv']).read_bytes()).hexdigest())
            self.assertIn('Preview metrics describe the original candidate',files['note'])

    def test_public_provenance_keeps_filename_and_remote_url_without_local_paths(self):
        source={'ephemeris_sources':{'Earth':[{'source':r'C:\Users\someone\Documents\Earth.txt'},
                                             {'source':'https://ssd.jpl.nasa.gov/api/horizons.api'}]}}
        cleaned=refresh.portable_report(source)
        self.assertEqual(cleaned['ephemeris_sources']['Earth'][0]['source'],'Local Horizons input: Earth.txt')
        self.assertEqual(cleaned['ephemeris_sources']['Earth'][1],source['ephemeris_sources']['Earth'][1])
        self.assertNotIn('someone',json.dumps(cleaned))


if __name__=='__main__':unittest.main()
