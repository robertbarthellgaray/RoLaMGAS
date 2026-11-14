"""Admission and reproducibility checks for the additional capacity sources."""
import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent


class InternationalCapacityTests(unittest.TestCase):
    def test_data_sources_are_distinct_and_same_in_app_and_site(self):
        app=json.loads((ROOT/'gui_assets/launch_performance_curves.json').read_text(encoding='utf-8'))
        website=json.loads((ROOT/'docs/data/launch_performance_curves.json').read_text(encoding='utf-8'))
        self.assertEqual(app,website)
        extra=[v for v in app['vehicles'] if v.get('international_id')]
        self.assertEqual(len(extra),4)
        for row in extra:
            self.assertTrue(row['source_url'].startswith('https://'));self.assertTrue(row['ground_rules'])
            self.assertEqual(row['points'],sorted(row['points']))
        for row in extra:
            if row['data_kind']=='published_historical_fit':
                lo,hi=row['valid_c3_range']
                for x,m in row['points']:
                    self.assertTrue(lo<=x<=hi);self.assertAlmostEqual(m,sum(a*x**i for i,a in enumerate(row['polynomial_ascending'])))
            if row['data_kind']=='published_study_point':self.assertEqual(row['points'],[[30.,3000.]])

    def test_unapproved_silverbird_numbers_remain_withheld(self):
        for filename in ('gui_assets/launch_performance_curves.json','gui_assets/international_launch_performance.json','docs/data/launch_performance_curves.json'):
            data=json.loads((ROOT/filename).read_text(encoding='utf-8'))
            for row in data['vehicles']:
                self.assertNotIn('silverbird',str(row.get('international_id','')).lower())
                self.assertNotIn('silverbirdastronautics.com',row.get('source_url',''))
        self.assertFalse((ROOT/'studies/international_launch_performance/silverbird_samples.json').exists())


if __name__=='__main__':unittest.main()
