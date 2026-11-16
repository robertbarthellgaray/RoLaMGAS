import unittest
from refresh_public_archive import download,admitted

class PublicArchiveTests(unittest.TestCase):
    def test_full_snapshot_follows_all_pages_and_keeps_high_watermark(self):
        pages=iter([{'candidates':[{'id':'new','received_at':'2026-11-16T00:00:00.000Z'}],'next_cursor':'older'},
                    {'candidates':[{'id':'old','received_at':'2026-11-15T00:00:00.000Z'}],'next_cursor':None}])
        rows,watermark=download('https://example.test',lambda url:next(pages))
        self.assertEqual(len(rows),2);self.assertEqual(watermark,'2026-11-16T00:00:00.000Z')

    def test_repeated_cursor_aborts_instead_of_publishing_partial_archive(self):
        with self.assertRaises(ValueError):download('https://example.test',lambda url:{'candidates':[],'next_cursor':'same'})

    def test_public_admission_keeps_yellow_and_existing_energy_limits(self):
        row={'id':'test','classification':'yellow','sequence':'EdvEJ','body_ids':['399','399','599'],
             'dates_jd_tdb':[2460000,2460600,2462000],'metrics':{'launch_c3_km2_s2':28}}
        self.assertTrue(admitted(row,{}));self.assertFalse(admitted(row,{'test':{}}))
        row['metrics']['launch_c3_km2_s2']=61
        self.assertFalse(admitted(row,{}))

if __name__=='__main__':unittest.main()
