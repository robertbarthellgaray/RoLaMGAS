"""Published study schedules must survive initialization without silent clipping."""
from pathlib import Path
from datetime import date
import json
import unittest
import numpy as np
from dynamics import Model
from ephemeris import jd
from historical_seeds import references,timing_guess
from mission_search import load_database,resolve_route

ROOT=Path(__file__).resolve().parent
DATA=json.loads((ROOT/'departure_seeds/decadal_missions.json').read_text(encoding='utf-8'))

class DecadalSeedTests(unittest.TestCase):
    def test_nine_sourced_timing_guesses_and_continuous_thrust_exclusion(self):
        catalog=json.loads((ROOT/'departure_seeds/decadal_sources.json').read_text(encoding='utf-8'))
        sources={r['id']:r['url'] for r in catalog['reports']}
        names={r['name'] for r in references()}
        self.assertEqual(sum(m['seed_eligible'] for m in DATA['missions']),9)
        for m in DATA['missions']:
            self.assertEqual(m['sources'],[sources[m['report_id']]])
            self.assertEqual(m['name'] in names,m['seed_eligible'])
            if not m['seed_eligible']:continue
            self.assertEqual(len(m['planet_leg_days']),len(m['bodies'])-1)
            self.assertGreaterEqual(m['c3'],5)
            self.assertTrue(all(d>0 for d in m['planet_leg_days']))
            if m.get('dates'):
                self.assertEqual(m['planet_leg_days'],[(date.fromisoformat(b)-date.fromisoformat(a)).days for a,b in zip(m['dates'],m['dates'][1:])])
    def test_all_study_leg_durations_fit_selected_routes_without_clipping(self):
        db=load_database()
        for m in DATA['missions']:
            if not m['seed_eligible']:continue
            with self.subTest(mission=m['name']):
                route=resolve_route(m['sequence'],db,m.get('target_object'))
                start=jd((m.get('dates') or [m['launch_start']])[0])
                model=Model(route,dict(launch_jd=[start,start],min_c3=5,max_c3=200),None)
                values=timing_guess(model,np.full(model.dimension,.5),m)
                np.testing.assert_allclose(np.diff(model.dates(values)),m['planet_leg_days'],atol=1e-8)
                self.assertEqual(model.config['min_c3'],5)
                self.assertEqual(model.config['max_c3'],200)
                for dsm in m.get('dsm_events',[]):
                    fraction=(jd(dsm['date'])-jd(m['dates'][dsm['leg_index']]))/m['planet_leg_days'][dsm['leg_index']]
                    self.assertAlmostEqual(dsm['fraction'],fraction)
    def test_conflicting_dates_and_unlocated_burns_are_not_invented(self):
        variants=[m for m in DATA['missions'] if m.get('ambiguity_group')=='ganymede_2010_earth2']
        self.assertEqual({m['dates'][3] for m in variants},{'2025-10-19','2025-10-29'})
        mercury=next(m for m in DATA['missions'] if m['name']=='Mercury Lander 2010 chemical study')
        self.assertEqual([d['leg_index'] for d in mercury['dsm_events']],[3,4,5])
        self.assertTrue(all(d['magnitude_kms'] is None for d in mercury['dsm_events']))
        titan=next(m for m in DATA['missions'] if m['name'].startswith('Titan Lake'))
        self.assertNotIn('dates',titan)
        self.assertNotIn('dsm_events',titan)

if __name__=='__main__':unittest.main()
