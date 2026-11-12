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
        self.assertEqual(len(extra),8)
        for row in extra:
            self.assertTrue(row['source_url'].startswith('https://'));self.assertTrue(row['ground_rules'])
            self.assertEqual(row['points'],sorted(row['points']))
        for row in extra:
            if row['data_kind']=='published_historical_fit':
                lo,hi=row['valid_c3_range']
                for x,m in row['points']:
                    self.assertTrue(lo<=x<=hi);self.assertAlmostEqual(m,sum(a*x**i for i,a in enumerate(row['polynomial_ascending'])))
            if row['data_kind']=='published_study_point':self.assertEqual(row['points'],[[30.,3000.]])

    def test_silverbird_ground_rules_intervals_and_variant_identity_survive(self):
        samples=json.loads((ROOT/'studies/international_launch_performance/silverbird_samples.json').read_text(encoding='utf-8'))
        data=json.loads((ROOT/'gui_assets/international_launch_performance.json').read_text(encoding='utf-8'))
        for i,v in enumerate(samples['vehicles']):
            row=next(r for r in data['vehicles'] if r.get('international_id')=='silverbird_'+str(i))
            for sample,point,interval in zip(v['rows'],row['points'],row['confidence95_points']):
                self.assertEqual(point,[sample['c3'],sample['capacity_kg']]);self.assertEqual(interval,[sample['c3'],*sample['confidence95_kg']])
                self.assertEqual(sample['request']['isEscape'],'1');self.assertEqual(sample['request']['inc'],'0');self.assertEqual(sample['request']['peri'],'200')
                self.assertEqual(sample['request']['Ttype'],'1');self.assertEqual(sample['request']['CalMode'],'2')
                self.assertTrue(interval[1]<=point[1]<=interval[2]);self.assertEqual(len(sample['source_html_sha256']),64)
            if i==0:
                self.assertNotIn('PSLV-XL',row['vehicle']);self.assertIn('variant unspecified',row['vehicle'])


if __name__=='__main__':unittest.main()
