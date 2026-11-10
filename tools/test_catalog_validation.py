import math
import unittest
from catalog_validation import audit_candidate

class AdmissionTests(unittest.TestCase):
    def example(self):
        # An Earth flyby with exactly matched excess speeds and a mild turn.
        angle=math.radians(10);vi=[8.,0.,0.];vo=[8*math.cos(angle),8*math.sin(angle),0.]
        q=dict(events=[dict(body=b,planet_state_km_kms=[0.]*6) for b in ['Earth','Earth','Jupiter']],
               dates_jd_tdb=[1.,2.,3.],departure_velocities_kms=[[5.,0.,0.],vo],arrival_velocities_kms=[vi,[9.,0.,0.]],
               launch_c3_km2_s2=25.,arrival_vinf_kms=9.,flybys=[dict(event_index=1)],dsms=[],total_dsm_kms=0.,duration_years=1.)
        bodies={'Earth':(399,398600.435436,6378.137,200.)}
        return q,bodies
    def test_vectors_overrule_false_pass_flag(self):
        q,b=self.example();q['arrival_velocities_kms'][0]=[9.,0.,0.];q['flybys'][0]['passes_speed_tolerance']=True
        self.assertFalse(audit_candidate(q,{},b)['passed'])
    def test_subsurface_turn_is_rejected(self):
        q,b=self.example();q['departure_velocities_kms'][1]=[-8.,0.,0.]
        self.assertFalse(audit_candidate(q,{},b)['passed'])
    def test_historical_missing_cap_does_not_bypass_current_cap(self):
        q,b=self.example();q['dsms']=[dict(magnitude_kms=.701,delta_v_ecliptic_j2000_kms=[.701,0.,0.])];q['total_dsm_kms']=.701
        self.assertFalse(audit_candidate(q,{},b)['passed'])
    def test_exact_speed_and_safe_turn_pass(self):
        q,b=self.example();self.assertTrue(audit_candidate(q,{},b)['passed'])
    def test_fake_low_burn_magnitude_is_rejected(self):
        q,b=self.example();q['dsms']=[dict(magnitude_kms=.1,delta_v_ecliptic_j2000_kms=[2.,0.,0.])];q['total_dsm_kms']=.1
        self.assertFalse(audit_candidate(q,{},b)['passed'])
    def test_powered_geometry_is_recovered_from_vectors_not_pass_flags(self):
        from powered_flyby import geometry
        q,b=self.example();q['departure_velocities_kms'][1]=[7.99*math.cos(math.radians(10)),7.99*math.sin(math.radians(10)),0.]
        power=geometry(b['Earth'][1],b['Earth'][2]+200,q['arrival_velocities_kms'][0],q['departure_velocities_kms'][1],1e7)
        q['flybys'][0]['powered_flyby']=power;q['total_dsm_kms']=power['magnitude_kms']
        self.assertTrue(audit_candidate(q,dict(powered_flybys=True),b)['passed'])
        power['peri_out_velocity_kms'][2]+=.01
        self.assertFalse(audit_candidate(q,dict(powered_flybys=True),b)['passed'])

if __name__=='__main__':unittest.main()
