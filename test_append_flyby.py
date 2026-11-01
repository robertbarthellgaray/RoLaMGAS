import bootstrap  # noqa: F401
import math,unittest
import numpy as np
from ephemeris import AU,MU_SUN,DAY,JD0
from mission_search import normalize,routes_for,coverage
from dynamics import Model
from append_flyby import extension_request
from candidate_refinement import neighborhood_request


class CircularEphemerides:
    def state(self,body,date):
        radius=AU*dict(Earth=1.,Venus=.723,Mercury=.387,Mars=1.524)[body]
        rate=math.sqrt(MU_SUN/radius**3);angle=(date-JD0)*DAY*rate
        return np.array([radius*math.cos(angle),radius*math.sin(angle),0.,
                         -radius*rate*math.sin(angle),radius*rate*math.cos(angle),0.])


class AppendTests(unittest.TestCase):
    def parent(self,dsm=False):
        c=normalize(dict(target='Venus',sequences=['EdvV' if dsm else 'EV'],max_c3=1000.,max_arrival_vinf_kms=1.))
        route=routes_for(c)[0];ep=CircularEphemerides();x=[.4,.3]+([.5,.5001,.4999,.5] if dsm else [])
        q=Model(route,c,ep).evaluate(x,[[0,True]])
        q.update(id='0123456789ab',status='near_miss_not_accepted')
        return c,route,q,ep

    def test_every_prefix_leg_and_date_remains_exactly_fixed(self):
        c,r,q,ep=self.parent()
        c=normalize(extension_request(c,r,q,'parent','Mercury',2,80,700))
        model=Model(routes_for(c)[0],c,ep)
        x=np.array(c['append_flyby']['seed_x']);x[:2]=[.02,.98]
        new=model.evaluate(x,[[0,True],[0,True],[1,True]])
        self.assertEqual(new['dates_jd_tdb'][:2],q['dates_jd_tdb'])
        self.assertEqual(new['segments'][:len(q['segments'])],q['segments'])
        self.assertEqual(new['departure_velocities_kms'][:1],q['departure_velocities_kms'])
        self.assertEqual(new['arrival_velocities_kms'][:1],q['arrival_velocities_kms'])
        self.assertEqual(new['launch_c3_km2_s2'],q['launch_c3_km2_s2'])
        self.assertEqual(len(model.free_indices),2)
        self.assertEqual(new['bodies'],['Earth','Venus','Mercury','Mercury'])

    def test_existing_dsms_remain_fixed_while_new_dsm_is_free(self):
        c,r,q,ep=self.parent(True)
        c=normalize(extension_request(c,r,q,'parent','Mercury',1,80,700,True))
        model=Model(routes_for(c)[0],c,ep)
        x=np.array(c['append_flyby']['seed_x']);x[:2]=.99;x[3:7]=.1
        new=model.evaluate(x,[[0,True],[0,True]])
        self.assertEqual(new['dsms'][0],q['dsms'][0]);self.assertEqual(len(new['dsms']),2)
        self.assertEqual(len(model.free_indices),5)
        np.testing.assert_array_equal(model.expand_variables(model.active_variables(x))[:2],q['x'][:2])

    def test_refining_an_extension_does_not_unlock_the_original_cruise(self):
        c,r,q,ep=self.parent()
        c=normalize(extension_request(c,r,q,'parent','Mercury',1,80,700))
        route=routes_for(c)[0];model=Model(route,c,ep)
        new=model.evaluate(c['append_flyby']['seed_x'],[[0,True],[0,True]])
        new.update(id='abcdef012345')
        request=neighborhood_request(c,route,new,'extension',20)
        refined=normalize(request);m=Model(routes_for(refined)[0],refined,ep)
        dates=m.dates(request['local_refinement']['seed_x'])
        self.assertEqual(dates[:2],q['dates_jd_tdb'])
        np.testing.assert_allclose(dates,new['dates_jd_tdb'],rtol=0,atol=1e-8)
        self.assertEqual(request['search_objective'],'arrival')

    def test_bad_controls_rejected_and_future_coverage_included(self):
        c,r,q,ep=self.parent()
        for controls in (dict(count=0),dict(count=4),dict(minimum_days=-1),dict(maximum_days=float('nan'))):
            with self.assertRaises(ValueError):extension_request(c,r,q,'parent',**controls)
        c=normalize(extension_request(c,r,q,'parent','Mercury',2,80,700))
        a,b=coverage(c,routes_for(c))
        self.assertEqual(a,q['dates_jd_tdb'][0]-2)
        self.assertEqual(b,q['dates_jd_tdb'][-1]+1400+2)


if __name__=='__main__':unittest.main()
