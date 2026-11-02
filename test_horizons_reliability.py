"""Deterministic comet selection and verified HTTPS trust contracts."""
import bootstrap  # noqa: F401
import io
import json
import os
from pathlib import Path
import ssl
import tempfile
import unittest
import urllib.error
from unittest.mock import patch, MagicMock

from ephemeris import jd
from horizons_targets import (TARGETS, command_for_epoch, identity, is_comet,
                              register_target, resolve, target_for_epoch)
import network


class HorizonsReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.targets = dict(TARGETS)

    def tearDown(self):
        TARGETS.clear()
        TARGETS.update(self.targets)

    def test_old_halley_identity_gets_pinned_apparition(self):
        old = dict(name='1P/Halley', id='1000036', command='DES=1P;',
                   kind='small_body', designation='1P', orbit_class='Halley-type Comet*')
        register_target(old)
        first = command_for_epoch(old['name'], jd('1984-01-01'))
        self.assertEqual(first, 'DES=1P;CAP<2445700.500000000;')
        # A subsequent download chunk must retain this mission's solution.
        self.assertEqual(command_for_epoch(old['name'], jd('1986-01-01')), first)
        self.assertEqual(identity(old['name'])['id'], '1000036')
        # A new mission deliberately re-pins even if the GUI has an old lookup.
        fresh = target_for_epoch(identity(old['name']), jd('2030-01-01'))
        self.assertEqual(fresh['command'], 'DES=1P;CAP<2462502.500000000;')
        self.assertEqual(old['command'], 'DES=1P;')

    def test_comet_lookup_keeps_retrograde_metadata_and_identity(self):
        lookup = dict(signature={'version':'1.1'}, result=[dict(
            spkid='1000036', name='Halley', pdes='1P', type='comet (integrated barycenter)')])
        sbdb = dict(object=dict(fullname='1P/Halley', spkid='1000036', des='1P'),
                    orbit=dict(elements=[dict(name='i',value='162.19'),
                                         dict(name='a',value='17.93'),
                                         dict(name='q',value='0.575')]),
                    phys_par=[dict(name='diameter',value='11.0',units='km',ref='fixture')])
        with patch('horizons_targets.request_json', side_effect=[lookup,sbdb]) as request:
            target = resolve('1P', epoch='1984-01-01')
        self.assertTrue(target['retrograde'])
        self.assertEqual(target['inclination_deg'],162.19)
        self.assertEqual(target['effective_radius_km'],5.5)
        self.assertIn('CAP<2445700.500000000;',target['command'])
        self.assertIn('spk=1000036',request.call_args_list[1].args[0])

    def test_halley_name_stays_ambiguous_without_silently_picking_asteroid(self):
        lookup = dict(signature={'version':'1.1'},result=[
            dict(spkid='20002688',name='2688 Halley',type='asteroid (integrated barycenter)'),
            dict(spkid='1000036',name='Halley',pdes='1P',type='comet (integrated barycenter)')])
        with patch('horizons_targets.request_json',return_value=lookup) as request:
            answer=resolve('Halley')
        self.assertTrue(answer['ambiguous'])
        self.assertEqual(request.call_count,1)
        self.assertNotIn('command',answer)

    def test_sbdb_cannot_substitute_a_different_small_body(self):
        lookup=dict(signature={'version':'1.1'},result=[dict(
            spkid='1000036',name='Halley',pdes='1P',type='comet (integrated barycenter)')])
        other=dict(object=dict(fullname='2688 Halley',spkid='20002688',des='2688'))
        with patch('horizons_targets.request_json',side_effect=[lookup,other]):
            with self.assertRaisesRegex(ValueError,'identity differs'):
                resolve('1P')

    def test_verified_https_context_and_json(self):
        response=MagicMock()
        response.__enter__.return_value=io.StringIO('{"valid":true}')
        with patch.dict(os.environ,{},clear=True), patch('network.urllib.request.urlopen',return_value=response) as opened:
            self.assertEqual(network.request_json('https://ssd.jpl.nasa.gov/example'),{'valid':True})
        context=opened.call_args.kwargs['context']
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        with self.assertRaisesRegex(ValueError,'HTTPS'):
            network.request_json('http://ssd.jpl.nasa.gov/example')

    def test_self_signed_chain_is_explained_and_never_retried_unverified(self):
        failure=urllib.error.URLError(ssl.SSLCertVerificationError(
            1,'certificate verify failed: self-signed certificate in certificate chain'))
        with patch('network.urllib.request.urlopen',side_effect=failure) as opened:
            with self.assertRaisesRegex(RuntimeError,'ROLAMGAS_CA_BUNDLE'):
                network.request_json('https://ssd.jpl.nasa.gov/example')
        self.assertEqual(opened.call_count,1)
        context=opened.call_args.kwargs['context']
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_custom_ca_bundle_is_loaded_without_disabling_checks(self):
        fake_context=MagicMock()
        with tempfile.TemporaryDirectory() as folder:
            pem=Path(folder)/'network-ca.pem'
            pem.write_text('fixture; context is mocked')
            with patch.dict(os.environ,{'ROLAMGAS_CA_BUNDLE':str(pem)},clear=True), \
                 patch('truststore.SSLContext',return_value=fake_context):
                context=network.tls_context()
            context.load_verify_locations.assert_called_once_with(cafile=str(pem))
            self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            with patch.dict(os.environ,{'ROLAMGAS_CA_BUNDLE':str(pem)+'missing'},clear=True):
                with self.assertRaisesRegex(ValueError,'does not exist'):
                    network.tls_context()

    def test_missing_native_package_uses_verified_stdlib_context(self):
        with patch.dict('sys.modules',{'truststore':None}), patch.dict(os.environ,{},clear=True):
            context=network.tls_context()
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)


if __name__=='__main__':
    unittest.main()
