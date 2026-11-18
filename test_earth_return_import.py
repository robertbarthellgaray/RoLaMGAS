import unittest
from mission_search import normalize,routes_for
from search_options import import_options

class EarthReturnImportTests(unittest.TestCase):
    def test_explicit_earth_return_sequence_imports_without_frozen_append_state(self):
        doc={'format':'rolamgas-search-options','schema_version':1,'settings':{'target':'Earth','sequences':['EMVE']}}
        result=import_options(doc)
        route=routes_for(normalize(result['config']))[0]
        self.assertEqual(route['bodies'],['Earth','Mars','Venus','Earth'])

    def test_incorrect_sequence_endpoint_is_still_rejected(self):
        with self.assertRaises(ValueError):routes_for(normalize({'target':'Earth','sequences':['EVJ']}))

if __name__=='__main__':unittest.main()
