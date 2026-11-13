import unittest
from expand_jupiter_library import jupiter_prefix,diversity_select
from community import encounter_key

class JupiterExpansionTests(unittest.TestCase):
    def test_prefix_drops_downstream_burns_without_changing_upstream_controls(self):
        r=dict(sequence='EdvEJdvU',body_ids=['399','399','599','799'],dates_jd_tdb=[1,2,3,4],branches=[[0,True],[0,True],[0,False]],dsm_controls=[dict(leg_index=0,fraction=.5),dict(leg_index=2,fraction=.6)])
        q=jupiter_prefix(r)
        self.assertEqual(q['sequence'],'EdvEJ');self.assertEqual(q['dates_jd_tdb'],[1,2,3]);self.assertEqual(q['dsm_controls'],r['dsm_controls'][:1]);self.assertEqual(len(r['branches']),3)
    def test_mercury_token_and_first_jupiter_event_are_preserved(self):
        r=dict(sequence='EMeVEEJSJX',body_ids=['399','199','299','399','399','599','699','599','999'],dates_jd_tdb=list(range(9)),branches=[[0,True]]*8,dsm_controls=[])
        q=jupiter_prefix(r);self.assertEqual(q['sequence'],'EMeVEEJ');self.assertEqual(len(q['body_ids']),6)
    def test_existing_encounter_days_and_near_duplicate_slots_are_excluded(self):
        def pair(day,seq='EJ'):
            r=dict(sequence=seq,body_ids=['399','599'],dates_jd_tdb=[2460000+day,2461000+day],id=str(day)+seq,metrics=dict(launch_c3_km2_s2=80,total_dsm_kms=0,arrival_vinf_kms=7,duration_years=3))
            return dict(launch_date='2030-01-01',launch_c3_km2_s2=80),r
        a,b=pair(0),pair(.1);c=pair(10)
        selected,count=diversity_select([a,b,c],{encounter_key(a[1])},10)
        self.assertEqual(count,1);self.assertEqual(selected,[c])

if __name__=='__main__':unittest.main()
