import unittest
import json,tempfile
from pathlib import Path
from unittest.mock import patch
import refresh_body_names as names

class BodyNameTests(unittest.TestCase):
    def test_comets_include_their_official_designation_and_name(self):
        with patch.object(names,'fetch',return_value=dict(result=[dict(spkid='1000025',name='Encke',pdes='2P',type='comet (integrated barycenter)')])):
            self.assertEqual(names.resolve_label('1000025')['name'],'2P/Encke')
    def test_exact_horizons_identity_ignores_similar_objects(self):
        with patch.object(names,'fetch',side_effect=[{},dict(result=[dict(spkid='20000001',name='Ceres'),dict(spkid='20010199',name='10199 Chariklo')])]):
            self.assertEqual(names.resolve_label('20010199')['name'],'10199 Chariklo')
    def test_sbdb_requires_exact_spk_and_preserves_current_name_and_classification(self):
        obj=dict(spkid='20136108',shortname='136108 Haumea',des='136108',kind='an',orbit_class=dict(code='TNO',name='TransNeptunian Object'))
        with patch.object(names,'fetch',return_value=dict(object=obj)):
            row=names.resolve_label('20136108');self.assertEqual(row['name'],'136108 Haumea');self.assertEqual(row['orbit_class_code'],'TNO')
        with patch.object(names,'fetch',side_effect=[dict(object=obj),dict(result=[])]):self.assertIsNone(names.resolve_label('20136199'))

    def test_live_refresh_paginates_from_receipt_watermark(self):
        since='2026-11-01T00:00:00.000Z';end='2026-11-02T00:00:00.000Z'
        with patch.object(names,'fetch',side_effect=[dict(candidates=[dict(body_ids=['399','20001036'],received_at=end)],next_cursor='next'),dict(candidates=[],next_cursor=None)]) as request:
            rows,watermark=names.live_rows('https://example.test',since)
        self.assertEqual(watermark,end);self.assertEqual(len(rows),1)
        self.assertIn('since=2026-11-01',request.call_args_list[0].args[0]);self.assertIn('cursor=next',request.call_args_list[1].args[0])

    def test_failed_lookup_preserves_existing_names_and_watermark_for_retry(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(names,'ROOT',Path(folder)),patch.object(names.time,'sleep'):
            root=Path(folder);(root/'docs/data').mkdir(parents=True)
            path=root/'docs/data/body_names.json';path.write_text(json.dumps(dict(schema_version=1,bodies={'20001036':dict(name='1036 Ganymed',horizons_id='20001036')},live_checked_through='old')))
            (root/'docs/data/community_seed_catalog.json').write_text(json.dumps(dict(candidates=[])))
            (root/'community_config.json').write_text(json.dumps(dict(endpoint='https://example.test')))
            with patch.object(names,'live_rows',return_value=([dict(body_ids=['399','20145452'])],'new')),patch.object(names,'resolve_label',side_effect=lambda ident:None if ident=='20145452' else dict(name='1036 Ganymed',horizons_id=ident,orbit_class='Amor')):
                result=names.refresh(live=True)
            self.assertEqual(result['bodies']['20001036']['name'],'1036 Ganymed');self.assertEqual(result['live_checked_through'],'old')

if __name__=='__main__':unittest.main()
