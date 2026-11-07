"""Release and installation safety tests with disposable paths only."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
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

    def external_snapshot_fixture(self):
        parent = Path(tempfile.gettempdir()).resolve()
        self.assertTrue(parent.is_dir())
        self.assertFalse(any((p / ".git").exists() for p in (parent, *parent.parents)),
                         "Snapshot test inputs require an external temporary directory")
        root = parent / ("skill snapshot release test " + uuid.uuid4().hex)
        root.mkdir()
        self.addCleanup(self.remove_external_snapshot_fixture, root, parent)
        repository = root / "configured repository"
        repository.mkdir()
        (repository / ".git").mkdir()
        workspace = root / "external feature with spaces"
        workspace.mkdir()
        (workspace / "specs").mkdir()
        ticket = b"Synthetic approved release smoke scope"
        specification = b"Synthetic approved release smoke specification"
        (workspace / "ticket.md").write_bytes(ticket)
        (workspace / "specs/0001.md").write_bytes(specification)
        digest = hashlib.sha256(specification).hexdigest()
        state = dict(schema_version=2, library_version="1.1.0", generation=1,
            feature_id="release-smoke", lifecycle="active",
            ticket_sha256=hashlib.sha256(ticket).hexdigest(),
            spec_revision=1, spec_sha256=digest,
            spec_approval=dict(human="Synthetic owner", evidence="Synthetic approval",
                               date="2026-11-06", revision=1, sha256=digest),
            tasks={"first": dict(status="pending", depends_on=[], owner=None,
                                 head=None, review=None)}, gates={}, integrated_head="b" * 40,
            integration=None, pr=None, merge=None, resources={},
            cleanup=None, cleanup_authorization=None)
        (workspace / "state.json").write_text(json.dumps(state), encoding="utf-8")
        config = dict(config_version="1.0.0",
            repositories=[dict(id="synthetic", path=str(repository))],
            workspaces=[dict(id="mapped", repository_id="synthetic", path=str(workspace))])
        config_path = root / "dashboard config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return root, config, config_path

    def remove_external_snapshot_fixture(self, root, parent):
        self.assertEqual(root.resolve().parent, parent)
        self.assertTrue(root.name.startswith("skill snapshot release test "))
        shutil.rmtree(root)

    @staticmethod
    def snapshot_fingerprint(root):
        return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                if p.is_file() else None for p in root.rglob("*")}

    def test_distributed_snapshot_resources_and_installed_entry_points(self):
        destination = self.directory / "installed snapshot skills with spaces"
        archive_path = self.directory / "snapshot release with spaces.zip"
        for script, flag, target in (
                ("install_library.py", "--destination", destination),
                ("package_library.py", "--output", archive_path)):
            command = [sys.executable, str(ROOT / "scripts" / script),
                       "--root", str(ROOT), flag, str(target)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            before = (self.snapshot_fingerprint(target) if target.is_dir()
                      else hashlib.sha256(target.read_bytes()).hexdigest())
            refused = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(1, refused.returncode, refused.stderr)
            after = (self.snapshot_fingerprint(target) if target.is_dir()
                     else hashlib.sha256(target.read_bytes()).hexdigest())
            self.assertEqual(before, after)
        manifest = json.loads((destination / "library-manifest.json").read_text())
        required = {
            "feature-workflow/scripts/snapshot.py",
            "feature-workflow/scripts/snapshot_model.py",
            "feature-workflow/references/snapshot.md",
            "feature-workflow/references/snapshot-schema.json",
            "feature-workflow/assets/snapshot-examples/complete.json",
            "feature-workflow/assets/snapshot-examples/partial.json",
            "feature-workflow/assets/snapshot-examples/unavailable.json",
            "feature-workflow/assets/snapshot-examples/config.json",
        }
        self.assertTrue(required <= manifest["files"].keys())
        self.assertFalse(any("__pycache__" in p or p.endswith((".pyc", ".pyo"))
                             for p in manifest["files"]))
        self.assertFalse((destination / "scripts").exists())
        with zipfile.ZipFile(archive_path) as archive:
            packaged = json.loads(archive.read("library-manifest.json"))
            self.assertEqual(manifest, packaged)
            for name in required:
                blob = archive.read(name)
                self.assertEqual(manifest["files"][name], hashlib.sha256(blob).hexdigest())
                self.assertEqual(blob, (destination / name).read_bytes())
        root, config, config_path = self.external_snapshot_fixture()
        partial = json.loads(json.dumps(config))
        partial["workspaces"].append(dict(id="missing", repository_id="synthetic",
                                          path=str(root / "missing workspace")))
        fatal = dict(config_version="99.0.0")
        paths = []
        for name, value, exit_code, completeness in (
                ("complete", config, 0, "complete"),
                ("partial", partial, 2, "partial"),
                ("fatal", fatal, 1, "unavailable")):
            path = root / (name + " dashboard.json")
            path.write_text(json.dumps(value), encoding="utf-8")
            paths.append((path, exit_code, completeness))
        reader = destination / "feature-workflow/scripts/snapshot.py"
        installed_before = self.snapshot_fingerprint(destination)
        inputs_before = self.snapshot_fingerprint(root)
        environment = os.environ.copy()
        environment.update(PYTHONPATH="", PATH="")
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        environment.pop("PYTHONPYCACHEPREFIX", None)
        for path, exit_code, completeness in paths:
            result = subprocess.run([sys.executable, str(reader), "--config", str(path)],
                cwd=root, env=environment, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(exit_code, result.returncode, result.stderr)
            envelope = json.loads(result.stdout)
            self.assertEqual(completeness, envelope["completeness"])
            self.assertEqual("1.0.0", envelope["contract_version"])
            self.assertEqual(manifest["library_version"], envelope["producer"]["library_version"])
            if exit_code != 1:
                self.assertEqual("release-smoke", envelope["features"][0]["feature_id"])
        bootstrap = (
            "import sys; sys.dont_write_bytecode=True; import importlib.util,json; "
            "spec=importlib.util.spec_from_file_location('installed_snapshot',sys.argv[1]); "
            "reader=importlib.util.module_from_spec(spec); spec.loader.exec_module(reader); "
            "print(json.dumps(reader.build_snapshot(json.loads(sys.argv[2]))))"
        )
        result = subprocess.run([sys.executable, "-c", bootstrap, str(reader), json.dumps(config)],
            cwd=root, env=environment, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("complete", json.loads(result.stdout)["completeness"])
        self.assertEqual(installed_before, self.snapshot_fingerprint(destination))
        self.assertEqual(inputs_before, self.snapshot_fingerprint(root))

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
