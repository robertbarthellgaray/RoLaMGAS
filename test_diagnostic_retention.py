import bootstrap  # noqa: F401
import json
from pathlib import Path
import tempfile
import unittest
from mission_search import summarize
from restore_diagnostics import restore


def candidate(index):
    return dict(sequence='EVVEEU',branches=[[0,True]],dates_jd_tdb=[2460000.5+index,2461000.5],
                x=[index/100,0.5],screening_residual_norm=float(index),status='near_miss_not_accepted')


class DiagnosticRetentionTests(unittest.TestCase):
    def test_over_limit_diagnostics_are_preserved(self):
        cap=dict(keep=100,max_single_dsm_kms=.7)
        bad_gap=candidate(0);bad_gap['max_vinf_mismatch_mps']=700.01
        bad_dsm=candidate(1);bad_dsm['dsms']=[dict(magnitude_kms=.701)]
        boundary=candidate(2);boundary['max_vinf_mismatch_mps']=700.;boundary['max_single_dsm_kms']=.7
        result=summarize([dict(accepted=[],near_misses=[bad_gap,bad_dsm,boundary])],cap)
        self.assertEqual(len(result['near_misses']),3)

    def test_more_than_ten_diagnostics_survive_summary_with_exact_duplicates_removed(self):
        diagnostics=[candidate(i) for i in range(40)]
        result=summarize([dict(accepted=[],near_misses=diagnostics+diagnostics[:2])],dict(keep=1))
        self.assertEqual(len(result['near_misses']),40)
        self.assertEqual(len(set(q['id'] for q in result['near_misses'])),40)

    def test_old_saved_checkpoints_restore_diagnostics_and_preserve_previous_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);(folder/'checkpoints').mkdir()
            (folder/'results.json').write_text(json.dumps(dict(candidates=[],near_misses=[candidate(0)])))
            (folder/'live.json').write_text('{}')
            (folder/'gui_status.json').write_text(json.dumps(dict(state='finished')))
            (folder/'checkpoints/a.json').write_text(json.dumps(dict(near_misses=[candidate(i) for i in range(25)])))
            result=restore(folder)
            self.assertEqual(result['after'],25)
            self.assertTrue((Path(result['backup'])/'live.json').is_file())
            self.assertFalse((folder/'live.json').exists())
            self.assertIsNone(restore(folder))


if __name__=='__main__':unittest.main()
