"""Offline checks for native release commands and package metadata."""
import tempfile
import zipfile
import unittest
from pathlib import Path
from unittest.mock import patch
import build_release as build


class NativeReleaseTests(unittest.TestCase):
    def test_native_commands_preserve_baseline_models_and_trust(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'project';root.mkdir()
            for name in build.DATA_FILES:
                path=root/name
                if name in ('examples','model_assets','gui_assets','third_party_licenses'):path.mkdir()
                else:path.touch()
            with patch.object(build,'ROOT',root):
                windows=build.pyinstaller_command('win32')
                mac=build.pyinstaller_command('darwin')
                linux=build.pyinstaller_command('linux')
            self.assertIn('--onefile',windows)
            self.assertNotIn('--onefile',mac)
            self.assertIn('--windowed',mac)
            self.assertIn('--osx-bundle-identifier',mac)
            self.assertIn('--onedir',linux)
            for command in (windows,mac,linux):
                self.assertIn('truststore',command)
                self.assertIn('network',command)
                self.assertTrue(any('baseline_ephemerides.zip' in x for x in command))
                self.assertTrue(any('model_assets' in x for x in command))
                self.assertTrue(any('gui_assets' in x for x in command))

    def test_clean_source_archive_has_rebuild_inputs_without_private_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'project';root.mkdir()
            required=('rolamgas.py','network.py','gui.html','gui.js','gui.css','gallery.html',
                'sequence_database.json','requirements.txt','requirements-build.txt',
                'Launch RoLaMGAS.cmd','Launch Mission Search.cmd','Launch GUI.ps1',
                'Launch Command Line.cmd','Setup Python.cmd','.gitignore','.gitattributes',
                'PUBLIC_README.md','baseline_ephemerides.zip','community_config.json','community_seed_catalog.json')
            for name in required:(root/name).write_text('fixture',encoding='utf-8')
            for name in ('gui_assets/chart.png','model_assets/spacecraft.3ds','runs/private.json',
                         'cache/private.json','.github/workflows/native-builds.yml'):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
            with patch.object(build,'ROOT',root),patch.object(build,'MODULES',['rolamgas','network']),patch.object(build,'DOCS',[]):
                output=build.source_release(root/'baseline_ephemerides.zip')
            with zipfile.ZipFile(output) as archive:
                names=archive.namelist()
                for name in ('network.py','requirements-build.txt','baseline_ephemerides.zip','community_config.json','community_seed_catalog.json',
                             'gui_assets/chart.png','model_assets/spacecraft.3ds',
                             '.github/workflows/native-builds.yml'):
                    self.assertIn('RoLaMGAS/'+name,names)
                self.assertFalse(any('/runs/' in name or '/cache/' in name for name in names))
                self.assertEqual(len(names),len(set(names)))

    def test_architectures_and_package_version(self):
        self.assertEqual(build.architecture('AMD64'),'amd64')
        self.assertEqual(build.architecture('x86_64'),'amd64')
        self.assertEqual(build.architecture('aarch64'),'arm64')
        self.assertEqual(build.architecture('arm64'),'arm64')
        for value in ('0.2.0','1.0.0-rc1','1.2.3+build1'):
            self.assertEqual(build.validate_version(value),value)
        for value in ('','main','../1.0','1.0\nDepends: bad','1.0;echo bad'):
            with self.assertRaises(ValueError):build.validate_version(value)

    def test_debian_control_is_installable_and_named(self):
        control=build.debian_control('0.2.0','amd64')
        self.assertIn('Package: rolamgas\n',control)
        self.assertIn('Architecture: amd64\n',control)
        self.assertIn('libc6 (>= 2.35)',control)
        self.assertIn('xdg-utils',control)
        self.assertTrue(control.endswith('\n'))


if __name__=='__main__':unittest.main()
