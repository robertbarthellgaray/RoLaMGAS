"""Adding or reordering routes must preserve each sequence's search trials."""
import bootstrap
import unittest
from unittest.mock import patch
from mission_search import normalize,routes_for,planned_jobs,job_search
from test_hard_c3_generation import CircularStates

ROUTES=['EdvEJ','EVEEJ','EVdvEEJ','EVVEJ','EVdvVEJ','EEVEEJ']

class SequenceIndependenceTests(unittest.TestCase):
    def config(self,sequences,**updates):
        return normalize(dict(target='Jupiter',sequences=sequences,**updates))
    def plans(self,c):
        return list(planned_jobs(c,routes_for(c)))
    def signature(self,jobs,sequence):
        return [(j[0],j[2],j[3],j[4],j[5]) for j in jobs if j[0]['id']==sequence]

    def test_grouped_routes_preserve_standalone_trials_and_budget(self):
        settings=dict(branch_families=6,samples_per_sequence=96,refinements_per_sequence=18,batches=2)
        grouped=self.plans(self.config(ROUTES,**settings))
        for sequence in ROUTES:
            standalone=self.plans(self.config([sequence],**settings))
            self.assertEqual(self.signature(grouped,sequence),self.signature(standalone,sequence))
        self.assertEqual(len({j[-1] for j in grouped}),len(grouped))

    def test_route_order_does_not_change_partial_branch_selection(self):
        a=self.plans(self.config(ROUTES,branch_families=3,batches=2))
        b=self.plans(self.config(list(reversed(ROUTES)),branch_families=3,batches=2))
        for sequence in ROUTES:self.assertEqual(self.signature(a,sequence),self.signature(b,sequence))

    def test_existing_successful_standalone_seed_is_preserved(self):
        c=self.config(ROUTES,samples_per_sequence=6000,refinements_per_sequence=72,branch_families=16)
        for sequence in ('EVEEJ','EVdvEEJ'):
            jobs=[j for j in self.plans(c) if j[0]['id']==sequence]
            branch=[[0,True],[0,True],[1,True],[0,True]]
            successful=next(j for j in jobs if j[2]==branch)
            self.assertEqual(successful[3],503)
            self.assertEqual(successful[4:6],(400,5))

    def test_worker_produces_same_scientific_candidates_alone_or_grouped(self):
        settings=dict(samples_per_sequence=32,refinements_per_sequence=2,max_nfev=8,branch_families=3,max_c3=1e5)
        single=self.plans(self.config(['EJ'],**settings))[0]
        group=next(j for j in self.plans(self.config(ROUTES+['EJ'],**settings)) if j[0]['id']=='EJ' and j[2]==single[2])
        with patch('mission_search._WORKER_EP',CircularStates()),patch('mission_search._PROGRESS_QUEUE',None):
            a=job_search(single);b=job_search(group)
        def scientific(result):
            return [(q['x'],q['dates_jd_tdb'],q['launch_c3_km2_s2'],q['total_dsm_kms'],q['screening_residual_norm']) for q in result['accepted']+result['near_misses']]
        self.assertTrue(scientific(a))
        self.assertEqual(scientific(a),scientific(b))

if __name__=='__main__':unittest.main()
