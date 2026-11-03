import bootstrap
import unittest
from datetime import date
from mission_search import load_database,normalize,routes_for
import build_database
import tempfile,json
from pathlib import Path
from unittest.mock import patch

class FastJupiterRouteTests(unittest.TestCase):
    def test_default_ranges_include_flown_fast_jupiter_leg(self):
        days=(date(2007,2,28)-date(2006,1,19)).days
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(build_database,"HERE",Path(folder)):build_database.build()
            generated=json.loads((Path(folder)/"sequence_database.json").read_text())
        for db in (load_database(),generated):
            lo,hi=db['pair_days']['Earth-Jupiter']
            self.assertLessEqual(lo,days);self.assertGreaterEqual(hi,days)
            for route in db['sequences']:
                for i,pair in enumerate(zip(route['bodies'],route['bodies'][1:])):
                    if pair==('Earth','Jupiter'):
                        self.assertLessEqual(route['leg_days'][i][0],days)
    def test_explicit_user_timing_override_stays_authoritative(self):
        c=normalize(dict(target='Jupiter',sequences=['EJ'],route_overrides={'EJ':{'leg_days':[[500,1800]]}}))
        self.assertEqual(routes_for(c)[0]['leg_days'],[[500,1800]])

if __name__=='__main__':unittest.main()
