from pathlib import Path
import json,unittest
from copy import deepcopy
from mission_search import normalize,routes_for
from trajectory_prefixes import public_records,prefix_route
from community import record_variables
from dynamics import Model
import numpy as np

class TrajectoryPrefixTests(unittest.TestCase):
    def fixture(self):
        doc=json.loads((Path(__file__).parent/'test_fixtures/planet_prefix_candidate.json').read_text(encoding='utf-8'))
        q=doc['candidate'];c=normalize(doc['config']);return q,c,routes_for(c)[0]
    def test_real_jpl_cruise_prefixes_recompute_arrival_and_drop_future_burns(self):
        q,c,route=self.fixture();old=deepcopy(q);records=public_records(q,c,route)
        by_sequence={r['sequence']:r for r in records}
        self.assertEqual(set(by_sequence),{'EVdvEEJX','EV','EVdvEEJ'})
        self.assertEqual(by_sequence['EV']['dsm_controls'],[]);self.assertEqual(by_sequence['EV']['metrics']['total_dsm_kms'],0)
        self.assertNotEqual(by_sequence['EV']['metrics']['arrival_vinf_kms'],q['arrival_vinf_kms'])
        self.assertEqual(by_sequence['EVdvEEJ']['body_ids'][-1],'599')
        self.assertEqual(q,old)
        for record in records:self.assertNotIn('cache',record);self.assertNotIn('config',record)
    def test_prefix_arrival_limit_is_rechecked(self):
        q,c,r=self.fixture();records=public_records(q,dict(c,max_arrival_vinf_kms=.01),r)
        self.assertEqual(len(records),1) # Parent eligibility is handled by its original caller.
    def test_low_energy_or_red_parent_never_produces_children(self):
        q,c,r=self.fixture();q['launch_c3_km2_s2']=0;self.assertEqual(public_records(q,c,r),[])
        q,c,r=self.fixture();q['periapsis_violation']=True;self.assertEqual(public_records(q,c,r),[])
    def test_route_token_slicing_handles_repeated_planets_and_later_dsms(self):
        q,c,r=self.fixture();p=prefix_route(r,1);self.assertEqual(p['id'],'EV');self.assertEqual(p['dsm_legs'],[])

if __name__=='__main__':unittest.main()
