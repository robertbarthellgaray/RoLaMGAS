"""Protect the public examples' physical admission and requested route coverage."""
import hashlib
import json
from pathlib import Path
import unittest

DOCS=Path(__file__).resolve().parents[1]/'docs'
def read(file):return json.loads(file.read_text(encoding='utf-8'))

class PublicCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index=read(DOCS/'data/index.json')['cases']
        cls.cases=[read(DOCS/'data/cases'/(c['id']+'.json')) for c in cls.index]
    def test_small_body_destinations_replace_previous_examples(self):
        planets={'Mercury','Venus','Earth','Mars','Jupiter','Saturn','Uranus','Neptune'}
        self.assertEqual({c['target'] for c in self.cases}-planets,{'Pluto','Eris','2026 ED138'})
    def test_each_requested_destination_has_multiple_assist_sequences(self):
        for target in ['Pluto','Eris','2026 ED138','Saturn','Neptune']:
            self.assertGreaterEqual(len({c['sequence'] for c in self.cases if c['target']==target}),3,target)
    def test_all_lambert_examples_meet_independent_admission(self):
        for c in self.cases:
            if c['model']!='Lambert candidate':continue
            with self.subTest(candidate=c['id']):
                v=c['validation'];self.assertTrue(v['passed']);self.assertEqual(v['reasons'],[])
                self.assertLessEqual(v['max_vinf_mismatch_mps'],1.000001)
                self.assertLessEqual(v['max_single_dsm_mps'],700.000001)
                self.assertLessEqual(v['max_powered_flyby_mps'],200.000001)
                self.assertLessEqual(v['max_coast_endpoint_error_km'],1.)
                self.assertLessEqual(v['max_reference_ephemeris_position_error_km'],.1)
                self.assertLessEqual(v['max_reference_ephemeris_velocity_error_mps'],.001)
                for join in v['joins']:
                    if join['clearance_above_floor_km'] is not None:self.assertGreaterEqual(join['clearance_above_floor_km'],-.001)
    def test_integrated_concepts_have_clearance_checks_and_unchanged_downloads(self):
        for c in self.cases:
            if not c['spotlight']:continue
            self.assertTrue(c['integration_validation']['passed'])
            clearances=c['integration_validation']['planet_clearances'];self.assertEqual(len(clearances),9)
            self.assertTrue(all(v['altitude_km']>0 for v in clearances.values()))
            self.assertEqual(hashlib.sha256((DOCS/c['download']).read_bytes()).hexdigest(),c['provenance']['sha256'])
    def test_catalog_files_match_index_without_retired_case_files(self):
        ids={c['id'] for c in self.index};self.assertEqual(len(ids),len(self.index))
        self.assertEqual(ids,{p.stem for p in (DOCS/'data/cases').glob('*.json')})
        for id in ids:self.assertTrue((DOCS/'images'/(id+'.svg')).is_file())

if __name__=='__main__':unittest.main()
