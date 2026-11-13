import unittest
from search_assist_families import jobs_for

class FamilyJobsTests(unittest.TestCase):
    def test_plan_preserves_physical_controls_and_separates_new_dsm_architectures(self):
        record=dict(id='seed',sequence='EVVEJS',dates_jd_tdb=[2463657.5,2463800.,2464200.,2464300.,2464800.,2466900.],
                    dsm_controls=[],metrics=dict(duration_years=8.8,max_vinf_mismatch_mps=.01))
        jobs=jobs_for([record])
        self.assertTrue(jobs)
        self.assertEqual({job['sequence'] for job in jobs},{'EVdvVEJS'})
        self.assertEqual(record['dsm_controls'],[])
        self.assertIn(8*365.25,[j['shift_days'] for j in jobs])

    def test_noisy_stored_flyby_is_not_used_as_a_passing_seed(self):
        record=dict(id='bad',sequence='EVVEJ',metrics=dict(duration_years=5,max_vinf_mismatch_mps=400))
        self.assertEqual(jobs_for([record]),[])

if __name__=='__main__':unittest.main()
