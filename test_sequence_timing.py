import unittest
from copy import deepcopy
from sequence_timing import PLANETS,complete_pairs,pair_bounds
from mission_search import load_database,resolve_route

class TimingBoundsTests(unittest.TestCase):
    def test_all_planet_pairs_have_bounds_and_existing_ranges_are_preserved(self):
        known={'Earth-Jupiter':[500,2000]};original=deepcopy(known);pairs=complete_pairs(known)
        self.assertEqual(len(pairs),64);self.assertEqual(known,original)
        self.assertEqual(pairs['Earth-Jupiter'],[500,2000])
        for a in PLANETS:
            for b in PLANETS:self.assertTrue(0<pairs[a+'-'+b][0]<pairs[a+'-'+b][1])
    def test_missing_legacy_mars_jupiter_route_does_not_raise(self):
        db=load_database();db['pair_days'].pop('Mars-Jupiter',None)
        route=resolve_route('EMJN',db)
        self.assertEqual(route['leg_days'][1],[250,2500])
    def test_fallbacks_distinguish_planets_and_other_bodies(self):
        self.assertEqual(pair_bounds('Neptune','Venus',{}),[30,20*365.25])
        self.assertEqual(pair_bounds('Jupiter','Centaur',{}),[30,50*365.25])

if __name__=='__main__':unittest.main()
