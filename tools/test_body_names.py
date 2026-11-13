import unittest
from unittest.mock import patch
import refresh_body_names as names

class BodyNameTests(unittest.TestCase):
    def test_comets_include_their_official_designation_and_name(self):
        with patch.object(names,'fetch',return_value=dict(result=[dict(spkid='1000025',name='Encke',pdes='2P',type='comet (integrated barycenter)')])):
            self.assertEqual(names.resolve_label('1000025')['name'],'2P/Encke')
    def test_exact_horizons_identity_ignores_similar_objects(self):
        with patch.object(names,'fetch',return_value=dict(result=[dict(spkid='20000001',name='Ceres'),dict(spkid='20010199',name='10199 Chariklo')])):
            self.assertEqual(names.resolve_label('20010199')['name'],'10199 Chariklo')
    def test_sbdb_fallback_requires_exact_spk_and_preserves_classification(self):
        obj=dict(spkid='20136108',shortname='136108 Haumea',des='136108',kind='an',orbit_class=dict(code='TNO',name='TransNeptunian Object'))
        with patch.object(names,'fetch',side_effect=[dict(result=[]),dict(object=obj)]):
            row=names.resolve_label('20136108');self.assertEqual(row['name'],'136108 Haumea');self.assertEqual(row['orbit_class_code'],'TNO')
        with patch.object(names,'fetch',side_effect=[dict(result=[]),dict(object=obj)]):self.assertIsNone(names.resolve_label('20136199'))

if __name__=='__main__':unittest.main()
