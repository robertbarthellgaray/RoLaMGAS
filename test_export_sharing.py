"""Export uploads contain only numeric science data and honor opt-out."""
import bootstrap
import gzip,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from export_sharing import bundle,publish

class ExportSharingTests(unittest.TestCase):
    def test_numeric_bundle_discards_paths_logs_and_unapproved_report_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'trajectory.xyzv').write_text('2460000 1 2 3 4 5 6\n2460001 2 3 4 4 5 6\n');(root/'burns.csv').write_text('kind,julian_date_tdb,magnitude_kms,dx_kms,dy_kms,dz_kms,private\nDSM,2460000.5,0.1,0.1,0,0,C:/Users/private\n');(root/'worker.log').write_text('private')
            report=dict(numerical_validation_passed=True,no_sample_bracketed_planet_or_sun_impacts=True,cache='C:/Users/private',exported_launch_c3_km2_s2=30,total_onboard_delta_v_kms=.1)
            with patch('celestia_package.export_report',return_value=report),patch('export_sharing.public_record',return_value={'id':'a'*64}):data,packed=bundle(root,{}, {}, {})
            self.assertEqual(json.loads(gzip.decompress(packed)),data);self.assertNotIn('private',gzip.decompress(packed).decode());self.assertEqual(data['burns'][0]['magnitude_kms'],.1)
            (root/'trajectory.xyzv').write_text('2460000 1 2 3 4 5 6\n2460000 2 3 4 4 5 6\n')
            with patch('celestia_package.export_report',return_value=report),patch('export_sharing.public_record',return_value={'id':'a'*64}),self.assertRaisesRegex(ValueError,'ordered'):bundle(root,{}, {}, {})

    def test_opt_out_performs_no_file_reads_or_network_calls(self):
        with patch('export_sharing.settings',return_value={'share_candidates':False,'endpoint':'https://example.test'}),patch('export_sharing.bundle',side_effect=AssertionError('No files')),patch('export_sharing.exchange',side_effect=AssertionError('No network')):
            self.assertEqual(publish(Path('unused'),{}, {}, {})['state'],'disabled')

if __name__=='__main__':unittest.main()
