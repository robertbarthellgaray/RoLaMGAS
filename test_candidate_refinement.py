import bootstrap  # noqa: F401
import unittest
import numpy as np
from mission_search import normalize,routes_for,branch_families,load_database
from dynamics import Model
from candidate_refinement import neighborhood_request
from mercury_returns import seed_returns,MERCURY_YEAR_DAYS


class RefinementTests(unittest.TestCase):
    def test_parent_dates_and_dsm_controls_survive_new_parameterization(self):
        c=normalize(dict(target='Jupiter',sequences=['EdvEJ'],launch_start='2032-01-01',launch_end='2033-01-01'))
        route=routes_for(c)[0];model=Model(route,c,None)
        x=[.4,.3,.6,.45,.501,.499,.502]
        q=dict(id='123456abcdef',sequence=route['id'],dates_jd_tdb=model.dates(x),x=x,branches=[[1,False],[0,True]],launch_c3_km2_s2=28.)
        request=neighborhood_request(c,route,q,'parent',30)
        refined=normalize(request);r=routes_for(refined)[0];new=Model(r,refined,None)
        np.testing.assert_allclose(new.dates(request['local_refinement']['seed_x']),q['dates_jd_tdb'],atol=1e-8,rtol=0)
        self.assertEqual(request['local_refinement']['seed_x'][3:],x[3:])
        self.assertEqual(request['sequences'],['EdvEJ']);self.assertEqual(request['search_objective'],'c3')
        self.assertEqual(request['max_dsm_kms'],c['max_dsm_kms'])
        self.assertLessEqual(request['max_c3'],28.000001)
        self.assertEqual(branch_families(r,1,123,q['branches'])[0],q['branches'])

    def test_short_legs_get_ordered_windows_and_invalid_spans_fail(self):
        c=normalize(dict(target='Venus',sequences=['EV']))
        r=routes_for(c)[0];dates=[c['launch_jd'][0]+5,c['launch_jd'][0]+15]
        q=dict(id='123456abcdef',dates_jd_tdb=dates,x=[.2,.3],branches=[[0,True]],launch_c3_km2_s2=30.)
        n=normalize(neighborhood_request(c,r,q,'parent',30))
        self.assertLess(n['event_windows_jd'][0][1],n['event_windows_jd'][1][0])
        for span in (0,-1,float('nan'),366):
            with self.assertRaises(ValueError):neighborhood_request(c,r,q,'parent',span)

    def test_mercury_seeds_are_within_bounds_and_near_repeated_orbits(self):
        c=normalize(dict(target='Mercury',sequences=['EVMeMeMe']))
        route=routes_for(c)[0];model=Model(route,c,None)
        samples=np.full((100,model.dimension),.5);branch=[[0,True],[0,True],[1,True],[2,True]]
        count=seed_returns(samples,model,branch,np.random.default_rng(1))
        self.assertEqual(count,50)
        self.assertTrue(np.all((samples>=0)&(samples<=1)))
        for leg in (2,3):
            a,b=route['leg_days'][leg];years=(a+samples[:count,leg+1]*(b-a))/MERCURY_YEAR_DAYS
            self.assertLess(np.max(np.abs(years-np.round(years))),.08)
        c['event_windows_jd']=[[0,1]]*model.n
        unchanged=samples.copy();self.assertEqual(seed_returns(samples,model,branch,np.random.default_rng(1)),0)
        np.testing.assert_array_equal(samples,unchanged)


if __name__=='__main__':unittest.main()
