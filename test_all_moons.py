import bootstrap
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from ephemeris import Ephemerides,DAY,jd
from moon_targets import MOON_SYSTEMS,CATALOG_SYSTEMS,target_options,canonical_parent,parent_parameters,register_parent,named_moon,validate_options,parent_search_identity
from horizons_targets import identity,register_target,satellite_parent

class AllMoonTests(unittest.TestCase):
    def test_complete_catalog_includes_planets_dwarfs_and_asteroids(self):
        self.assertGreater(len(MOON_SYSTEMS),500)
        self.assertGreater(sum(len(target_options(p)) for p in MOON_SYSTEMS),950)
        for name in ('Earth','Mars','Jupiter','Saturn','Uranus','Neptune','Pluto','Eris','Haumea','Makemake','Quaoar','Orcus','Patroclus','Didymos'):
            self.assertTrue(target_options(name),name)
        self.assertEqual({m['name'] for m in target_options('Pluto')},{'Charon','Nix','Hydra','Kerberos','Styx'})

    def test_eris_aliases_share_dysnomia_and_real_parent_constants(self):
        for name in ('Eris','136199 Eris (2003 UB313)','Eris (system barycenter)','Eris (primary body)','20136199','920136199'):
            self.assertEqual(canonical_parent(name),'Eris')
            moon=target_options(name)[0];self.assertEqual(moon['id'],'120136199');self.assertTrue(moon['targeting_available'])
            self.assertNotIn('unavailable_reason',moon)
        parent=parent_parameters('Eris');self.assertEqual(parent[0],920136199);self.assertAlmostEqual(parent[1],1079.2);self.assertEqual(parent[2],1163.)
        self.assertEqual(named_moon('Dysnomia')['parent_body'],'Eris')
        self.assertEqual(parent_search_identity('Eris')['command'],'136199;')

    def test_known_moon_search_intent_can_be_saved_for_eris(self):
        from gui import App
        from mission_search import normalize
        with tempfile.TemporaryDirectory() as directory,patch('gui.HERE',Path(directory)),patch('gui.ensure_data'):
            app=App();moon=app.lookup('Dysnomia','2051-04-01')
            parent=app.targets['eris'];self.assertEqual(parent['kind'],'small_body')
            config=normalize(dict(target_object=parent,sequences=['EJSNX'],moon_target=dict(parent='Eris',moon_id=moon['id'])))
            self.assertEqual(config['moon_target']['moon_name'],'Dysnomia')

    def test_radius_unknown_means_center_distance_and_never_claims_surface_impact(self):
        moon=next(m for m in target_options('Jupiter') if m.get('radius_unknown'))
        self.assertEqual(moon['radius_km'],0.);self.assertEqual(moon['gm'],0.)
        option=validate_options('Jupiter',moon['id'],'approach',100)
        self.assertEqual(option['altitude_km'],100)
        with self.assertRaisesRegex(ValueError,'no measured radius'):validate_options('Jupiter',moon['id'],'impact',0)
        self.assertEqual(satellite_parent(dict(id=moon['id'],kind='horizons_object')),'Jupiter')

    def test_missing_small_body_models_are_explicit_and_not_invented(self):
        moon=target_options('Makemake')[0];self.assertFalse(moon['targeting_available'])
        with self.assertRaisesRegex(ValueError,'No verified'):validate_options('Makemake',moon['id'],'approach',100)
        self.assertIsNone(named_moon(moon['id']))

    def test_projection_is_boolean_and_off_by_default(self):
        self.assertFalse(validate_options('Eris','120136199','approach',100)['allow_projection'])
        self.assertTrue(validate_options('Eris','120136199','approach',100,allow_projection=True)['allow_projection'])
        with self.assertRaisesRegex(ValueError,'boolean'):validate_options('Eris','120136199','approach',100,allow_projection='true')

    def test_projected_cache_is_opt_in_and_preserves_binary_barycenter(self):
        from moon_ephemerides import project,MODEL
        from dynamics import kepler
        start=jd('2051-03-31');end=jd('2051-04-03');system=CATALOG_SYSTEMS['Eris'];moon=target_options('Eris')[0]
        bary_name=system['fullname'];bary=np.array([1e10,2e9,3e8,0.,0.,0.])
        class Bary:
            manifest={bary_name:[dict(source='controlled test barycenter')]}
            def state(self,body,date):return bary.copy()
        def tables(cache,bodies,*args,**kwargs):
            return Bary() if bodies==[bary_name] else Ephemerides(cache,bodies,*args,**kwargs)
        register_parent('Eris');register_target(dict(identity('Eris'),allow_projected_ephemeris=True))
        register_target(dict(name='Dysnomia',id='120136199',command='120136199',kind='natural_satellite',parent_body='Eris',allow_projected_ephemeris=True))
        with tempfile.TemporaryDirectory() as folder,patch('moon_ephemerides.Ephemerides',side_effect=tables):
            primary=project(folder,'Eris',start,end,.1,lambda message:None)
            satellite=project(folder,'Dysnomia',start,end,.1,lambda message:None)
            date=(start+end)/2;p=primary.state('Eris',date);m=satellite.state('Dysnomia',date)
            np.testing.assert_allclose((system['gm']*p+moon['gm']*m)/(system['gm']+moon['gm']),bary,atol=3e-6,rtol=0)
            state=np.array(moon['reference_relative_state_km_kms']);r,v=kepler(state[:3],state[3:],(date-moon['reference_epoch_jd_tdb'])*DAY,system['gm']+moon['gm'])
            np.testing.assert_allclose((m-p)[:3],r,atol=.002,rtol=0)
            self.assertEqual(primary.manifest['Eris'][0]['ephemeris_model'],MODEL)
            register_target(dict(identity('Dysnomia'),allow_projected_ephemeris=False))
            with self.assertRaisesRegex(ValueError,'No cached'):Ephemerides(folder,['Dysnomia'],start,end,.1)

if __name__=='__main__':unittest.main()
