"""Public CLI output/exit and bytecode nonmutation tests."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
from test_snapshot_reader import ReaderFixture, SCRIPT, reader, dump, hash_tree


class SnapshotCliTests(ReaderFixture, unittest.TestCase):
    def cli(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], text=True,
                                encoding="utf-8", capture_output=True, timeout=30, cwd=self.root)
        self.assertEqual("", result.stderr)
        value = json.loads(result.stdout)
        self.assertIsInstance(value, dict)
        return result, value

    def config_file(self, config=None):
        path = self.root / "dashboard config.json"
        dump(path, self.config if config is None else config)
        return path

    def test_complete_cli_from_any_working_directory_has_one_json_envelope(self):
        path = self.config_file()
        result, value = self.cli("--config", str(path))
        self.assertEqual(0, result.returncode)
        self.assertEqual("complete", value["completeness"])
        self.assertEqual(1, len(value["features"]))

    def test_partial_and_fatal_exit_codes_are_distinct(self):
        self.config["workspaces"].append(self.explicit(self.features / "missing", "missing"))
        result, value = self.cli("--config", str(self.config_file()))
        self.assertEqual(2, result.returncode)
        self.assertEqual(1, len(value["features"]))
        result, value = self.cli("--config", str(self.root / "absent.json"))
        self.assertEqual(1, result.returncode)
        self.assertEqual("unavailable", value["completeness"])

    def test_argument_errors_return_json_not_argparse_prose(self):
        for args in ([], ["--unknown"], ["--config", "relative.json"]):
            result, value = self.cli(*args)
            self.assertEqual(1, result.returncode)
            self.assertEqual("INVALID_CONFIG", value["diagnostics"][0]["code"])

    def test_duplicate_or_nonfinite_configuration_is_fatal(self):
        path = self.config_file()
        for raw in ('{"config_version":"1.0.0","config_version":"1.0.0"}',
                    '{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}', '{"value":1e999}'):
            path.write_text(raw, encoding="utf-8")
            result, value = self.cli("--config", str(path))
            self.assertEqual(1, result.returncode)
            self.assertEqual("INVALID_CONFIG", value["diagnostics"][0]["code"])

    def test_configuration_inside_repository_is_not_consumed(self):
        path = self.repo / "private config.json"
        dump(path, self.config)
        result, value = self.cli("--config", str(path))
        self.assertEqual(1, result.returncode)
        self.assertEqual([], value["features"])

    def test_held_lock_and_read_does_not_create_workflow_or_bytecode_files(self):
        (self.workspace / ".workflow.lock").write_text("synthetic writer")
        path = self.config_file()
        before, runtime_before = hash_tree(self.root), hash_tree(SCRIPT.parent)
        result, value = self.cli("--config", str(path))
        self.assertEqual(0, result.returncode)
        self.assertEqual(before, hash_tree(self.root))
        self.assertEqual(runtime_before, hash_tree(SCRIPT.parent))

    def fresh_consumer(self, name, bootstrap="", flags=()):
        runtime = self.root / name
        runtime.mkdir()
        for source in (SCRIPT, SCRIPT.with_name("snapshot_model.py")):
            shutil.copy2(source, runtime / source.name)
        target = runtime / SCRIPT.name
        before = hash_tree(runtime)
        program = (bootstrap +
            "import importlib.util,json;"
            "s=importlib.util.spec_from_file_location('fresh_consumer',%r);"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
            "print(json.dumps(m.build_snapshot(%r)['completeness']))"
        ) % (str(target), self.config)
        environment = dict(os.environ)
        for key in ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"):
            environment.pop(key, None)
        result = subprocess.run([sys.executable, *flags, "-c", program], text=True,
                                capture_output=True, timeout=30, env=environment, cwd=self.root)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('"complete"', result.stdout.strip())
        return before, hash_tree(runtime)

    def test_supported_callable_bootstraps_never_cache_on_first_load(self):
        for name, bootstrap, flags in (
                ("flag consumer", "", ("-B",)),
                ("explicit consumer", "import sys;sys.dont_write_bytecode=True;", ())):
            with self.subTest(name=name):
                before, after = self.fresh_consumer(name, bootstrap, flags)
                self.assertEqual(before, after)

    @unittest.skipUnless(sys.implementation.name == "cpython", "CPython importer boundary")
    def test_default_import_is_outside_supported_no_cache_bootstrap(self):
        # CPython caches source before its first line runs. This isolated probe
        # documents why callable consumers must disable caching before import.
        before, after = self.fresh_consumer("unsupported default importer")
        self.assertNotEqual(before, after)
        self.assertTrue(any("__pycache__" in p for p in after))

    def test_malformed_source_version_is_null_in_partial_wire_envelope(self):
        healthy = self.make_workspace("healthy CLI", feature_id="healthy")
        self.config["workspaces"].append(self.explicit(healthy, "healthy"))
        value = self.state()
        value["schema_version"] = -1
        value["generation"] = True
        self.save(value)
        result, envelope = self.cli("--config", str(self.config_file()))
        self.assertEqual(2, result.returncode)
        self.assertEqual(["healthy"], [f["feature_id"] for f in envelope["features"]])
        source = next(s for s in envelope["sources"] if s["workspace_id"] == "mapped")
        self.assertIsNone(source["schema_version"])
        self.assertIsNone(source["generation"])
        self.assertIn("INVALID_SOURCE", [d["code"] for d in source["diagnostics"]])

    def test_uri_evidence_is_not_remote_verification(self):
        value = self.state()
        value["visibility"]["control"] = dict(owner_role="orchestrator", execution_authorized=True,
            evidence=dict(kind="uri", target="https://synthetic.invalid/approval", base=None,
                          sha256=None, revision=None, artifact_id="approval"))
        self.save(value)
        result, snapshot = self.cli("--config", str(self.config_file()))
        self.assertEqual(0, result.returncode)
        self.assertIsNone(snapshot["features"][0]["tasks"][0]["readiness"]["start_eligible"])
        reference = next(a for a in snapshot["features"][0]["artifacts"] if a["kind"] == "uri")
        self.assertEqual("not_recorded", reference["availability"]["reason"])


if __name__ == "__main__":
    unittest.main()
