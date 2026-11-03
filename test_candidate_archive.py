"""Known feasible trajectories survive new bounds only after full revalidation."""
import bootstrap
from copy import deepcopy
import json,tempfile,unittest
from pathlib import Path
import numpy as np
from candidate_archive import collect_candidates
from dynamics import Model
from mission_search import normalize,routes_for,summarize
from test_hard_c3_generation import CircularStates

class CandidateArchiveTests(unittest.TestCase):
    def parent(self,sequence='EJ'):
        target={'EJ':'Jupiter','EdvM':'Mars','EJU':'Uranus'}[sequence]
        c=normalize(dict(target=target,sequences=[sequence],launch_start='2030-01-01',launch_end='2031-01-01',max_c3=1e9,max_arrival_vinf_kms=1000,max_dsm_kms=1000,max_single_dsm_kms=1000,max_years=100))
        r=routes_for(c)[0];ep=CircularStates();x=[.4,.5] if sequence=='EJ' else [.4,.5,.5] if sequence=='EJU' else [.5,.4,.5,.51,.49,.5]
        q=Model(r,c,ep).evaluate(x,[o[0] for o in r['branch_options']]);q.update(id='abcdef123456',status='passes_configured_patched_conic_screen')
        return c,r,ep,q
    def save(self,folder,c,r,q,name='older'):
        p=Path(folder)/name;p.mkdir();(p/'run_manifest.json').write_text(json.dumps(dict(config=c,routes=[r])))
        (p/'results.json').write_text(json.dumps(dict(candidates=[q])))
        return p
    def test_narrower_c3_retains_a_known_valid_candidate_even_at_other_starting_boundary(self):
        c,r,ep,q=self.parent();self.assertTrue(Model(r,c,ep).accepted(q))
        current=dict(c,min_c3=max(6.25,q['launch_c3_km2_s2']-1),effective_min_c3=max(6.25,q['launch_c3_km2_s2']-1),max_c3=q['launch_c3_km2_s2']+1,c3_seed_boundary='maximum')
        with tempfile.TemporaryDirectory() as folder:
            self.save(folder,c,r,q);result=collect_candidates(current,[r],ep,folder)
        self.assertEqual(len(result['accepted']),1);new=result['accepted'][0]
        self.assertEqual(new['x'],q['x']);self.assertEqual(new['dates_jd_tdb'],q['dates_jd_tdb'])
        self.assertEqual(new['launch_c3_km2_s2'],q['launch_c3_km2_s2']);self.assertTrue(new['reused_from']['revalidated'])
    def test_new_energy_limit_rejects_before_later_legs_even_if_old_summary_is_forged(self):
        c,r,ep,q=self.parent('EJU');energy=q['launch_c3_km2_s2'];q['launch_c3_km2_s2']=0
        current=dict(c,max_c3=energy-1)
        ep.calls.clear()
        with tempfile.TemporaryDirectory() as folder:
            self.save(folder,c,r,q);result=collect_candidates(current,[r],ep,folder)
        self.assertEqual(result['accepted'],[]);self.assertNotIn('Uranus',ep.calls)
        self.assertEqual(result['stats']['rejected'],1)
    def test_new_arrival_and_individual_burn_limits_are_rechecked(self):
        for sequence in ('EJ','EdvM'):
            c,r,ep,q=self.parent(sequence);current=dict(c)
            if sequence=='EJ':current['max_arrival_vinf_kms']=q['arrival_vinf_kms']/2
            else:current['max_single_dsm_kms']=q['max_single_dsm_kms']/2
            with tempfile.TemporaryDirectory() as folder:
                self.save(folder,c,r,q);result=collect_candidates(current,[r],ep,folder)
            self.assertEqual(result['accepted'],[])
    def test_incompatible_date_or_dsm_parameterization_is_not_reinterpreted(self):
        c,r,ep,q=self.parent('EdvM')
        for changes in (dict(launch_jd=[c['launch_jd'][0]+1,c['launch_jd'][1]]),dict(dsm_velocity_box_kms=12.)):
            with tempfile.TemporaryDirectory() as folder:
                self.save(folder,c,r,q);result=collect_candidates(dict(c,**changes),[r],ep,folder)
            self.assertEqual(result['stats']['compatible'],0)
    def test_duplicate_or_incomplete_runs_do_not_break_collection(self):
        c,r,ep,q=self.parent()
        with tempfile.TemporaryDirectory() as folder:
            self.save(folder,c,r,q);self.save(folder,c,r,q,'duplicate')
            (Path(folder)/'incomplete').mkdir();(Path(folder)/'incomplete/results.json').write_text('{')
            result=collect_candidates(c,[r],ep,folder)
        self.assertEqual(len(result['accepted']),1)
    def test_archived_candidate_is_not_counted_as_a_completed_branch(self):
        c,r,ep,q=self.parent();q['screening_residual_norm']=0
        result=summarize([],c,[q])
        self.assertEqual(result['completed_jobs'],0);self.assertEqual(result['reused_candidates'],1)
        self.assertEqual(len(result['candidates']),1)

if __name__=='__main__':unittest.main()
