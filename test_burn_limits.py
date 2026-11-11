import bootstrap  # noqa: F401
import copy
import unittest
import numpy as np
from dynamics import Model
from mission_search import normalize


class BurnLimitTests(unittest.TestCase):
    def model_and_candidate(self):
        model=object.__new__(Model);model.config=normalize(dict(powered_flybys=True,max_dsm_kms=10))
        model.bodies=['Earth','Jupiter']
        q=dict(launch_c3_km2_s2=20,arrival_vinf_kms=3,duration_years=2,total_dsm_kms=.9,
               dsms=[dict(magnitude_kms=.7)],flybys=[dict(passes_powered_geometry=True,powered_flyby=dict(magnitude_kms=.2))])
        return model,q

    def test_defaults_and_exact_boundary(self):
        model,q=self.model_and_candidate()
        self.assertEqual(model.config['max_single_dsm_kms'],.7)
        self.assertEqual(model.config['max_powered_flyby_kms'],.2)
        self.assertTrue(model.accepted(q))

    def test_individual_caps_reject_even_with_large_total_budget(self):
        model,q=self.model_and_candidate()
        for kind in ('dsm','powered'):
            trial=copy.deepcopy(q)
            if kind=='dsm':trial['dsms'][0]['magnitude_kms']=.70001
            else:trial['flybys'][0]['powered_flyby']['magnitude_kms']=.20001
            self.assertFalse(model.accepted(trial))

    def test_limit_is_vector_norm_not_component_bound(self):
        model,q=self.model_and_candidate()
        q['dsms'][0]['magnitude_kms']=float(np.linalg.norm([.5,.5,0]))
        self.assertFalse(model.accepted(q))

    def test_zero_caps_are_valid_and_invalid_limits_rejected(self):
        c=normalize(dict(max_single_dsm_kms=0,max_powered_flyby_kms=0))
        self.assertEqual(c['max_single_dsm_kms'],0)
        for value in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):normalize(dict(max_single_dsm_kms=value))


if __name__=='__main__':unittest.main()
