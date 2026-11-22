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
        self.assertEqual(len(extra),5)
        for row in extra:
            self.assertTrue(row['source_url'].startswith('https://'));self.assertTrue(row['ground_rules'])
            self.assertEqual(row['points'],sorted(row['points']))
        for row in extra:
            if row['data_kind']=='published_historical_fit':
                lo,hi=row['valid_c3_range']
                for x,m in row['points']:
                    self.assertTrue(lo<=x<=hi);self.assertAlmostEqual(m,sum(a*x**i for i,a in enumerate(row['polynomial_ascending'])))
            if row['data_kind']=='published_study_point':self.assertEqual(row['points'],[[30.,3000.]])

    def test_lvm3_is_bounded_and_explicitly_estimated(self):
        data=json.loads((ROOT/'docs/data/launch_performance_curves.json').read_text(encoding='utf-8'))
        row=next(v for v in data['vehicles'] if v.get('international_id')=='nsil2025_lvm3_estimate')
        self.assertEqual(row['data_kind'],'calibrated_stage_estimate')
        self.assertEqual(row['display_rounding_kg'],100)
        self.assertEqual(row['valid_c3_range'],[0,30])
        self.assertLess(row['source_c3_range'][1],0)
        self.assertIn('not published positive-C3 performance',row['ground_rules'])
        self.assertTrue(all(a[1]>b[1]>0 for a,b in zip(row['points'],row['points'][1:])))
        self.assertEqual(row['points'][0][0],0)
        self.assertEqual(row['points'][-1][0],30)

    def test_permitted_silverbird_samples_have_provenance_and_no_extrapolation(self):
        app=json.loads((ROOT/'gui_assets/launch_performance_curves.json').read_text(encoding='utf-8'))
        rows=[r for r in app['vehicles'] if r.get('silverbird_id')]
        self.assertEqual(len(rows),17)
        for row in rows:
            self.assertEqual(row['source_url'],'https://silverbirdastronautics.com/LVperform.html')
            self.assertTrue(row['countries']);self.assertTrue(row['retrieved_at'])
            self.assertNotIn('extrapolation',row);self.assertNotIn('kickstage_id',row)
            self.assertEqual(len(row['points']),len(row['queries']))
            self.assertEqual(row['points'],sorted(row['points']))
            for q in row['queries']:
                self.assertEqual(q['fields']['peri'],'200')
                self.assertEqual(q['fields']['inc'],'0')
                self.assertEqual(len(q['source_html_sha256']),64)
            for c3,lo,hi in row['confidence95_points']:
                mass=dict(row['points'])[c3]
                self.assertLessEqual(lo,mass);self.assertGreaterEqual(hi,mass)


if __name__=='__main__':unittest.main()
