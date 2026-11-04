import unittest
from quality import assess_candidates


def candidate(id,c3=40,years=8,vinf=6,dv=.5,launch=2465000,target='599'):
    return dict(id=id,body_ids=['399',target],dates_jd_tdb=[launch,launch+years*365.25],
        launch_c3_km2_s2=c3,duration_years=years,arrival_vinf_kms=vinf,total_dsm_kms=dv)

class QualityTests(unittest.TestCase):
    def test_both_wasteful_costs_discouraged_retroactively(self):
        low=candidate('low'); high=candidate('high',80,16)
        result=assess_candidates([high], [low])
        self.assertEqual(result['high']['better_candidate_id'],'low')
        self.assertEqual(result['high']['tier'],1)
        self.assertNotIn('quality',high)

    def test_arrival_and_burn_tradeoffs_are_preserved(self):
        rows=[candidate('fast'),candidate('capture',80,16,2),candidate('fuel',80,16,6,.1)]
        self.assertTrue(all(v['tier']==2 for v in assess_candidates(rows).values()))

    def test_different_targets_and_launch_opportunities_not_compared(self):
        q=candidate('q',80,16)
        alternatives=[candidate('other',target='899'),candidate('later',launch=2465000+731)]
        self.assertEqual(assess_candidates([q],alternatives)['q']['compared_count'],0)

    def test_invalid_geometry_cannot_dominate_good_candidate(self):
        q=candidate('good',80,16); bad=candidate('bad')
        bad['max_vinf_mismatch_mps']=101
        self.assertEqual(assess_candidates([q],[bad])['good']['tier'],2)
        self.assertEqual(assess_candidates([bad])['bad']['tier'],0)

    def test_numerical_noise_is_not_material_improvement(self):
        q=candidate('q'); near=candidate('near',39.99,7.9999,5.9999,.4999)
        self.assertEqual(assess_candidates([q],[near])['q']['tier'],2)

    def test_public_records_and_legacy_cards_share_target(self):
        low=candidate('seed'); low['metrics']={k:low.pop(k) for k in ('launch_c3_km2_s2','duration_years','arrival_vinf_kms','total_dsm_kms')}
        high=candidate('legacy',80,16); high.pop('body_ids'); high['launch_date']='2030-01-01T12:00:00';high.pop('dates_jd_tdb')
        from datetime import datetime,timezone
        low['dates_jd_tdb'][0]=datetime(2030,1,1,12,tzinfo=timezone.utc).timestamp()/86400+2440587.5
        self.assertEqual(assess_candidates([high],[low],target='Jupiter')['legacy']['tier'],1)

    def test_nonfinite_unresolved_mismatch_cannot_dominate(self):
        q=candidate('good',80,16)
        for value in (float('nan'),float('inf')):
            bad=candidate('bad');bad['max_unresolved_vinf_mismatch_mps']=value
            self.assertEqual(assess_candidates([q],[bad])['good']['tier'],2)
            self.assertEqual(assess_candidates([bad])['bad']['tier'],0)

    def test_per_flyby_unresolved_geometry_overrides_aggregate_flags(self):
        q=candidate('good',80,16)
        for flags in ({'maneuver_budget_complete':True},{'powered_geometry_valid':True},
                      {'max_unresolved_vinf_mismatch_mps':0}):
            bad=candidate('bad');bad.update(flags)
            bad['flybys']=[{'speed_mismatch_mps':350,'passes_powered_geometry':False}]
            self.assertEqual(assess_candidates([q],[bad])['good']['tier'],2)
            self.assertEqual(assess_candidates([bad])['bad']['tier'],0)

    def test_constructed_powered_flybys_are_not_unresolved(self):
        low=candidate('powered');low['powered_geometry_valid']=True
        low['flybys']=[{'speed_mismatch_mps':350,'passes_powered_geometry':True}]
        high=candidate('high',80,16)
        self.assertEqual(assess_candidates([high],[low])['high']['better_candidate_id'],'powered')

    def test_actual_encounter_epochs_determine_flight_duration(self):
        low=candidate('low');high=candidate('high',80,16)
        high['duration_years']=.1
        self.assertEqual(assess_candidates([high],[low])['high']['better_candidate_id'],'low')
        bad=candidate('bad');bad['dates_jd_tdb'][-1]=bad['dates_jd_tdb'][0]-1
        self.assertEqual(assess_candidates([bad])['bad']['tier'],0)

class LegacyDateTests(unittest.TestCase):
    def test_actual_legacy_gallery_tdb_suffix_is_compared(self):
        q=candidate('legacy',80,16);q.pop('dates_jd_tdb');q['launch_date']='2030-01-01T12:00:00 TDB'
        low=candidate('low');low.pop('dates_jd_tdb');low['launch_date']='2030-01-01T12:00:00 TDB'
        self.assertEqual(assess_candidates([q],[low])['legacy']['tier'],1)

if __name__=='__main__':unittest.main()
