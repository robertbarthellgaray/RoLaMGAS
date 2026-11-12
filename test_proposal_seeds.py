"""Concept timing references stay sourced, portable and physically revalidated."""
from pathlib import Path
import json,unittest
import bootstrap
import numpy as np
from ephemeris import jd
from dynamics import Model
from historical_seeds import references,timing_guess
from mission_search import normalize,routes_for
from trajectory_transfer import materialize

ROOT=Path(__file__).resolve().parent
DATA=json.loads((ROOT/'departure_seeds/new_frontiers_missions.json').read_text(encoding='utf-8'))

class ProposalSeedsTests(unittest.TestCase):
    def test_only_representable_concept_timings_enter_the_seed_loader(self):
        loaded={m['name'] for m in references()}
        for mission in DATA['missions']:
            self.assertEqual(mission['name'] in loaded,mission['seed_eligible'])
            self.assertTrue(mission['sources']);self.assertGreaterEqual(mission['c3'],5)
            self.assertEqual(mission['planet_leg_days'],[jd(b)-jd(a) for a,b in zip(mission['dates'],mission['dates'][1:])])
            if not mission['seed_eligible']:
                self.assertTrue(any(d['fraction']<.1 for d in mission['dsm_events']))
    def test_study_presets_preserve_dates_and_reported_burn_locations(self):
        for mission in DATA['missions']:
            if not mission['seed_eligible']:continue
            path=ROOT/'examples'/('proposal_'+mission['name'].replace(' ','_')+'.json')
            config=normalize(json.loads(path.read_text(encoding='utf-8')));model=Model(routes_for(config)[0],config,None)
            point=timing_guess(model,np.full(model.dimension,.5),mission)
            np.testing.assert_allclose(model.dates(point),[jd(day) for day in mission['dates']],atol=1e-9,rtol=0)
            for d in mission.get('dsm_events',[]):
                k=model.n+4*model.dsm_legs.index(d['leg_index'])
                self.assertAlmostEqual(.1+.8*point[k],d['fraction'])
    def test_exact_camilla_handoff_recomputes_and_rejects_a_tighter_dsm_budget(self):
        q=json.loads((ROOT/'studies/camilla_2026/candidate.json').read_text(encoding='utf-8'))
        document=json.loads((ROOT/'studies/camilla_2026/selected-trajectory.json').read_text(encoding='utf-8'))
        class Events:
            def state(self,body,date):
                event=next(e for e in q['events'] if e['body']==body and abs(e['julian_date_tdb']-date)<1e-7)
                return np.array(event['planet_state_km_kms'])
        config=normalize(q['study_config']);route=routes_for(config)[0]
        fresh=materialize(document['trajectory'],config,route,Events())
        self.assertEqual(fresh['status'],'passes_configured_patched_conic_screen')
        self.assertLess(fresh['max_vinf_mismatch_mps'],.001)
        self.assertAlmostEqual(fresh['total_dsm_kms']*1000,313.75111394,places=5)
        self.assertTrue(all(f['conservative_equal_speed_altitude_km']>=f['minimum_altitude_km'] for f in fresh['flybys']))
        restricted=normalize(dict(q['study_config'],max_dsm_kms=.3,max_single_dsm_kms=.3))
        fresh=materialize(document['trajectory'],restricted,routes_for(restricted)[0],Events())
        self.assertNotEqual(fresh['status'],'passes_configured_patched_conic_screen')

if __name__=='__main__':unittest.main()
