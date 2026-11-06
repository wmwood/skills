"""Release and installation safety tests with disposable paths only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import unittest
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from install_library import install
from package_library import package
from validate_library import REQUIRED, validate


class LibraryTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / 'tmp'
        temporary_root.mkdir(exist_ok=True)
        # Python 3.14's private tempfile ACLs can prevent sandbox child access
        # on Windows. Use an ordinary unique directory with inherited ACLs.
        self.directory = temporary_root / ('skill library test ' + uuid.uuid4().hex)
        self.directory.mkdir()
        self.addCleanup(shutil.rmtree, self.directory)

    def test_repository_structure(self):
        self.assertEqual([], validate(ROOT))

    def test_package_manifest_and_no_overwrite(self):
        destination = self.directory / 'release with spaces.zip'
        package(ROOT, destination)
        before = destination.read_bytes()
        with zipfile.ZipFile(destination) as archive:
            manifest = json.loads(archive.read('library-manifest.json'))
            self.assertEqual(2, manifest['schema_version'])
            self.assertEqual(REQUIRED, {name.split('/')[0] for name in manifest['files']})
            for name, digest in manifest['files'].items():
                self.assertEqual(digest, hashlib.sha256(archive.read(name)).hexdigest())
        with self.assertRaises(FileExistsError):
            package(ROOT, destination)
        self.assertEqual(before, destination.read_bytes())

    def test_install_complete_and_existing_destination(self):
        destination = self.directory / 'installed skills with spaces'
        install(ROOT, destination)
        manifest = json.loads((destination / 'library-manifest.json').read_text())
        for name, digest in manifest['files'].items():
            self.assertEqual(digest, hashlib.sha256((destination / name).read_bytes()).hexdigest())
        sentinel = destination / 'owner file.txt'
        sentinel.write_text('preserve me')
        with self.assertRaises(FileExistsError):
            install(ROOT, destination)
        self.assertEqual('preserve me', sentinel.read_text())

    def test_structural_negative_cases(self):
        fixture = self.directory / 'invalid library'
        shutil.copytree(ROOT / 'skills', fixture / 'skills', ignore=shutil.ignore_patterns('__pycache__'))
        skill = fixture / 'skills' / 'ticket-writer' / 'SKILL.md'
        skill.write_text(skill.read_text(encoding='utf-8').replace('name: ticket-writer', 'name: wrong-name') + '\n[missing](missing.md)\nREPLACE: unfinished\n', encoding='utf-8')
        errors = validate(fixture)
        self.assertTrue(any('mismatched name' in error for error in errors))
        self.assertTrue(any('broken link' in error for error in errors))
        self.assertTrue(any('unfinished placeholder' in error for error in errors))
        destination = self.directory / 'must not exist'
        with self.assertRaises(ValueError):
            install(fixture, destination)
        self.assertFalse(destination.exists())

    def test_single_platform_commands_rejected(self):
        fixture = self.directory / 'shell coverage'
        fixture.mkdir()
        (fixture / 'README.md').write_text('```bash\npython "check.py"\n```\n', encoding='utf-8')
        self.assertTrue(any('shell examples need paired' in error for error in validate(fixture)))

    def test_dangling_destination_symlink_rejected(self):
        link = self.directory / 'already reserved link'
        missing_target = self.directory / 'must stay absent'
        try:
            link.symlink_to(missing_target)
        except OSError as error:
            self.skipTest(f'OS does not permit symbolic links: {error}')
        for operation in (install, package):
            with self.assertRaises(FileExistsError):
                operation(ROOT, link)
        self.assertFalse(missing_target.exists())


if __name__ == '__main__':
    unittest.main()
