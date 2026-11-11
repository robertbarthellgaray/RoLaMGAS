import unittest
from unittest.mock import patch
import numpy as np
from mission_search import normalize,routes_for
from dynamics import Model,C3BoundsError
from test_hard_c3_generation import CircularStates
from cost_refinement import boundary_seed
from trajectory_policy import c3_ceiling,public_energy_reason

class VenusDeparturePolicyTests(unittest.TestCase):
    def model(self,seq='EVEEJ',**updates):
        target='Mercury' if seq=='EVMe' else 'Jupiter'
        c=normalize(dict(target=target,sequences=[seq],max_c3=100,**updates))
        return Model(routes_for(c)[0],c,CircularStates())
    def test_route_cap_uses_lower_bound_and_leaves_other_routes_unchanged(self):
        self.assertEqual(self.model().c3_maximum,30)
        for seq in ('EJ','EdvEJ','EVMe'):self.assertEqual(self.model(seq).c3_maximum,100)
        self.assertEqual(c3_ceiling(['Earth','Venus','Jupiter'],dict(max_c3=20)),20)
        self.assertEqual(self.model(max_venus_c3=70).c3_maximum,70)
        self.assertEqual(self.model(max_venus_c3=None).c3_maximum,100)
    def test_above_cap_is_rejected_before_later_planets_are_queried(self):
        m=self.model();x=np.full(m.dimension,.5);branches=[[0,True]]*4
        with patch.object(m,'launch_solution',return_value=dict(c3=31)),patch.object(m.ep,'state',side_effect=AssertionError('Later planet queried')):
            with self.assertRaises(C3BoundsError):m.evaluate(x,branches)
    def test_maximum_boundary_projection_uses_route_cap(self):
        m=self.model(c3_seed_boundary='maximum');x=np.full(m.dimension,.5);branches=[[0,True]]*4
        m.route['leg_days'][0]=[90,500]  # Isolate energy projection from the separate timing-range regression.
        q=boundary_seed(m,x,branches);self.assertIsNotNone(q)
        self.assertAlmostEqual(m.launch_c3(q,branches),30,delta=2e-6)
    def test_conflicting_floor_is_reported_and_override_survives_portable_options(self):
        with self.assertRaisesRegex(ValueError,'Venus-assisted'):self.model(min_c3=35)
        from search_options import export_options,import_options
        c=normalize(dict(target='Jupiter',sequences=['EVEEJ'],min_c3=35,max_c3=60,max_venus_c3=None))
        document=export_options(c)['document']
        self.assertIsNone(import_options(document)['config']['max_venus_c3'])
    def test_may_2031_family_fits_default_timing_and_is_explicitly_scheduled(self):
        from mission_search import branch_families
        m=self.model();self.assertLessEqual(m.route['leg_days'][0][0],80)
        self.assertGreaterEqual(m.route['leg_days'][1][1],676)
        self.assertIn([[0,True],[1,False],[1,True],[0,True]],branch_families(m.route,4,502))
    def test_public_policy_is_explicitly_separate_from_physical_acceptance(self):
        for value in (float('nan'),-1,True):
            with self.assertRaises(ValueError):normalize(dict(max_venus_c3=value))
        self.assertIsNotNone(public_energy_reason(dict(body_ids=['399','299','599'],metrics=dict(launch_c3_km2_s2=31))))
        self.assertIsNone(public_energy_reason(dict(body_ids=['399','399','599'],metrics=dict(launch_c3_km2_s2=60))))
if __name__=='__main__':unittest.main()
