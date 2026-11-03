"""Historical imports preserve original passes and recover legacy physical controls."""
import json
from pathlib import Path
import tempfile
import unittest
import test_community as fixtures
from tools.import_passing_history import project,build

class HistoryImportTests(unittest.TestCase):
    def sample(self,sequence='EJ'):
        c,r,ep,q=fixtures.CommunityTests().parent(sequence)
        q['discovered_unix']=1704067200.;q['status']='passes_configured_patched_conic_screen'
        return c,r,q
    def test_preserves_original_budget_classification_and_only_public_fields(self):
        c,r,q=self.sample();q['launch_c3_km2_s2']=1.;q['private_file']='C:/Users/private/person';q['username']='person'
        record=project('unused',q,c,[r]);self.assertEqual(record['metrics']['launch_c3_km2_s2'],1.)
        self.assertEqual(record['classification'],'pass');self.assertEqual(record['body_ids'],['399','599'])
        self.assertNotIn('private',json.dumps(record));self.assertNotIn('username',record)
    def test_recovers_physical_dsm_when_gallery_omits_optimizer_variables(self):
        c,r,q=self.sample('EdvM');expected=project('unused',q,c,[r])
        q.pop('x');actual=project('unused',q,c,[])
        a,b=expected['dsm_controls'][0],actual['dsm_controls'][0]
        self.assertEqual(a['leg_index'],b['leg_index']);self.assertAlmostEqual(a['fraction'],b['fraction'],places=8)
        for x,y in zip(a['departure_offset_kms'],b['departure_offset_kms']):self.assertAlmostEqual(x,y,places=8)
    def test_resolves_thin_summary_and_deduplicates_using_production_validator(self):
        c,r,q=self.sample();thin={k:q[k] for k in ['id','status','sequence']}
        entries=[('unused',q,c,[r]),('unused-summary',thin,c,[r])]
        with tempfile.TemporaryDirectory() as folder:
            doc,report=build(entries,Path(folder)/'catalog.json',Path(folder)/'report.json')
            self.assertEqual(len(doc['candidates']),1);self.assertEqual(report['resolved_summary_references'],1)
            self.assertEqual(report['projection_failures'],0);self.assertEqual(report['schema_failures'],0)
            self.assertEqual(json.loads((Path(folder)/'catalog.json').read_text())['schema_version'],1)
if __name__=='__main__':unittest.main()
