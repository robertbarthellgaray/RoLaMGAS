import bootstrap
import unittest,numpy as np
from integrate_export import heliocentric_orbit_summary
from ephemeris import AU,MU_SUN,DAY,jd
from dynamics import kepler
class SolarOrbitDiagnosticsTests(unittest.TestCase):
    def test_ellipse_reports_aphelion_and_forward_epoch(self):
        a=3*AU;e=.7;rp=a*(1-e);v=np.sqrt(MU_SUN*(1+e)/rp);epoch=jd('2032-01-01')
        d=heliocentric_orbit_summary([rp,0,0,0,v,0],epoch)
        self.assertTrue(d['sun_bound']);self.assertAlmostEqual(d['aphelion_au'],5.1,places=10)
        self.assertAlmostEqual(d['next_aphelion_jd_tdb']-epoch,d['period_years']*365.25/2,places=7)
        r,_=kepler(np.array([rp,0,0]),np.array([0,v,0]),(d['next_aphelion_jd_tdb']-epoch)*DAY)
        self.assertAlmostEqual(np.linalg.norm(r)/AU,d['aphelion_au'],places=8)
    def test_hyperbola_has_no_aphelion_and_circular_orbit_no_unique_apo_epoch(self):
        d=heliocentric_orbit_summary([AU,0,0,0,50,0],2463000.5)
        self.assertFalse(d['sun_bound']);self.assertNotIn('next_aphelion_date',d)
        c=heliocentric_orbit_summary([AU,0,0,0,np.sqrt(MU_SUN/AU),0],2463000.5)
        self.assertTrue(c['sun_bound']);self.assertNotIn('next_aphelion_date',c)
    def test_very_long_bound_period_keeps_numeric_diagnostics_without_calendar_overflow(self):
        speed=np.sqrt(2*MU_SUN/AU)*(1-1e-7)
        d=heliocentric_orbit_summary([AU,0,0,0,speed,0],2463000.5)
        self.assertTrue(d['sun_bound']);self.assertGreater(d['period_years'],1e6)
        self.assertIsNone(d['next_aphelion_date'])
    def test_ixion_archive_state_is_outbound_but_sun_bound(self):
        state=np.array([3737968169.3397403,2332669825.9132442,-990163059.8874451,3.9953040543646803,3.4639785749063505,-.6619722306005094])
        d=heliocentric_orbit_summary(state,2480263.701806597)
        self.assertTrue(d['sun_bound']);self.assertGreater(d['radial_velocity_kms'],5.2)
        self.assertAlmostEqual(d['aphelion_au'],57.932042595,places=6)
        self.assertTrue(d['next_aphelion_date'].startswith('2141-12-04'))
        r,v=kepler(state[:3],state[3:],2*365.25*DAY)
        self.assertGreater(np.linalg.norm(r),np.linalg.norm(state[:3]));self.assertGreater(r@v,0)
if __name__=='__main__':unittest.main()
