import bootstrap  # noqa: F401
import unittest
import numpy as np
from ephemeris import AU,DAY
from integrate_export import planet_pieces,post_flyby_pieces,MONTH_DAYS,validate_post_flyby_months


class LinearPlanet:
    def state(self,body,date):
        return np.array([AU,30*(date-2463000.5)*DAY,0,0,30,0])


class PostFlybyTests(unittest.TestCase):
    def setup_node(self):
        ep=LinearPlanet();date=2463000.5
        node=planet_pieces('Earth',date,ep,uin=np.array([8.,0,0]),altitude=200,terminal=True)
        incoming=node['pieces'][0]['state'](date)
        return ep,node,incoming

    def test_zero_duration_keeps_endpoint_and_invalid_duration_fails(self):
        ep,node,initial=self.setup_node()
        self.assertEqual(post_flyby_pieces(node,ep,node['date'],initial),[])
        self.assertEqual(validate_post_flyby_months(0),0)
        self.assertEqual(validate_post_flyby_months(.5),.5)
        for value in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):validate_post_flyby_months(value)

    def test_outgoing_arc_is_continuous_and_moves_away_from_periapsis(self):
        ep,node,initial=self.setup_node();end=node['date']+.05
        pieces=post_flyby_pieces(node,ep,end,initial)
        self.assertEqual(len(pieces),1)
        np.testing.assert_allclose(pieces[0]['state'](node['date']),initial,atol=1e-5)
        relative=pieces[0]['state'](end)-ep.state('Earth',end)
        self.assertGreater(np.linalg.norm(relative[:3]),node['rp'])
        self.assertEqual(pieces[-1]['end'],end)

    def test_soi_exit_has_no_position_or_velocity_reset(self):
        ep,node,initial=self.setup_node();end=node['date']+3*MONTH_DAYS
        pieces=post_flyby_pieces(node,ep,end,initial)
        self.assertEqual(len(pieces),2)
        self.assertEqual(pieces[1]['kind'],'solar')
        join=pieces[0]['end']
        np.testing.assert_allclose(pieces[0]['state'](join),pieces[1]['state'](join),atol=1e-10)
        self.assertEqual(pieces[-1]['end'],end)
        self.assertLess(pieces[-1]['numerical_error_km'],1)

    def test_custom_body_continues_from_actual_incoming_velocity(self):
        date=2463000.5;initial=np.array([AU,0,0,0,30,0])
        node=dict(date=date,body='Example asteroid')
        pieces=post_flyby_pieces(node,None,date+MONTH_DAYS,initial)
        self.assertEqual(pieces[0]['kind'],'solar')
        np.testing.assert_allclose(pieces[0]['state'](date),initial,atol=1e-12)


if __name__=='__main__':unittest.main()
