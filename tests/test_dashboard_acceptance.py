"""Public dashboard snapshot acceptance using declarative synthetic fixtures."""
import sys
sys.dont_write_bytecode = True  # Required before loading the reader or model.

from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/dashboard"
SCRIPT = ROOT / "skills/feature-workflow/scripts/snapshot.py"
SPEC = importlib.util.spec_from_file_location("acceptance_snapshot", SCRIPT)
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)
CATALOG = json.loads((FIXTURES / "catalog.json").read_text(encoding="utf-8"))
NOW = CATALOG["observation_time"]


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fingerprint(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()
    }


def pointer(value, expression):
    for part in expression.strip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def apply_patch(value, operation):
    parts = operation["path"].strip("/").split("/")
    target = value
    for part in parts[:-1]:
        target = target[part]
    if operation["op"] == "delete":
        del target[parts[-1]]
    else:
        target[parts[-1]] = deepcopy(operation["value"])


class DashboardAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(os.environ.get("WORKFLOW_TEST_TMP", tempfile.gettempdir())).resolve()
        self.root = self.parent / ("dashboard acceptance " + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(self.remove_root)
        self.repo = self.root / "configured repository"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.features = self.root / "external feature locations"
        self.features.mkdir()
        self.config = dict(
            config_version="1.0.0",
            repositories=[dict(id="repo", path=str(self.repo))],
            workspaces=[],
            freshness_seconds=3600,
            max_read_attempts=3,
        )

    def remove_root(self):
        self.assertEqual(self.root.resolve().parent, self.parent)
        self.assertTrue(self.root.name.startswith("dashboard acceptance "))
        for path in self.root.rglob("*"):
            if not path.is_symlink():
                path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        shutil.rmtree(self.root)

    def fixture(self, case=None, name="feature with spaces cafÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©", identity="workspace"):
        workspace = self.features / name
        workspace.mkdir()
        artifacts = json.loads((FIXTURES / "artifacts.json").read_text(encoding="utf-8"))
        state = json.loads((FIXTURES / "base-state.json").read_text(encoding="utf-8"))
        if case:
            for operation in case["patches"]:
                apply_patch(state, operation)
            artifacts.update(case["extra_files"])
        for relative, content in artifacts.items():
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.encode("utf-8"))
        dump(workspace / "state.json", state)
        if case and case["raw_state"] is not None:
            (workspace / "state.json").write_text(case["raw_state"], encoding="utf-8")
        if case:
            for relative in case["remove_files"]:
                (workspace / relative).unlink()
        self.config["workspaces"].append(
            dict(id=identity, repository_id="repo", path=str(workspace))
        )
        return workspace

    def state(self, workspace):
        return json.loads((workspace / "state.json").read_text(encoding="utf-8"))

    def snapshot(self, config=None):
        return reader.build_snapshot(self.config if config is None else config, now=NOW)

    def assert_expected(self, snapshot, expected):
        self.assertEqual("1.0.0", snapshot["contract_version"])
        self.assertEqual(expected["feature_count"], len(snapshot["features"]))
        self.assertEqual(expected["completeness"], snapshot["completeness"])
        codes = {item["code"] for item in snapshot["diagnostics"]}
        self.assertTrue(set(expected["diagnostic_codes"]) <= codes, codes)
        self.assertFalse(set(expected["absent_diagnostic_codes"]) & codes, codes)
        for path, value in expected["paths"].items():
            self.assertEqual(value, pointer(snapshot, path), path)
        schema = json.loads((ROOT / "skills/feature-workflow/references/snapshot-schema.json").read_text())
        definitions = schema["$defs"]
        for source in snapshot["sources"]:
            self.assertTrue(set(definitions["source"]["required"]) <= source.keys())
        for feature in snapshot["features"]:
            self.assertTrue(set(definitions["feature"]["required"]) <= feature.keys())
            for kind, rows in (
                ("task", feature["tasks"]), ("blocker", feature["blockers"]),
                ("feedback", feature["feedback"]), ("assignment", feature["assignments"]),
                ("artifact", feature["artifacts"]),
            ):
                for row in rows:
                    self.assertTrue(set(definitions[kind]["required"]) <= row.keys(), kind)
            canonical_ids = [item["id"] for item in feature["artifacts"] if item["id"] is not None]
            self.assertEqual(len(canonical_ids), len(set(canonical_ids)))
        self.assertEqual(NOW, snapshot["generated_at"])
        for source in snapshot["sources"]:
            self.assertEqual(NOW, source["observed_at"])

    def test_catalogued_public_snapshots_and_diagnostics(self):
        for case in CATALOG["cases"]:
            with self.subTest(case=case["id"]):
                self.config["workspaces"] = []
                workspace = self.fixture(case, name=case["id"])
                before = fingerprint(workspace)
                first = self.snapshot()
                self.assert_expected(first, case["expected"])
                self.assertEqual(first, self.snapshot(), "Fixed-clock results must be deterministic")
                self.assertEqual(before, fingerprint(workspace))
                if case["raw_state"] is None and (workspace / "state.json").exists():
                    state_sha = hashlib.sha256((workspace / "state.json").read_bytes()).hexdigest()
                    if first["sources"][0]["state_sha256"] is not None:
                        self.assertEqual(state_sha, first["sources"][0]["state_sha256"])

    def test_pending_integration_needs_real_recorded_operation_evidence(self):
        valid = dict(task="build", source_head="a" * 40, parent="b" * 40,
                     spec_revision=1, phase="prepared")
        cases = [
            ({"invalid": "no operation evidence"}, "unknown", "INVALID_METADATA"),
            (dict(task="build", parent="b" * 40, spec_revision=1, phase="prepared"),
             "unknown", "INVALID_METADATA"),
            (dict(valid, source_head=[]), "unknown", "INVALID_METADATA"),
            (dict(valid, phase="made-up"), "unknown", "UNKNOWN_STATUS"),
            (dict(valid, phase="committed", commit="d" * 40), "unknown", "UNKNOWN_STATUS"),
            (dict(valid, parent="c" * 40), "obsolete", "INVALID_METADATA"),
            (valid, "current", None),
        ]
        for index, (intent, currency, code) in enumerate(cases):
            with self.subTest(intent=intent):
                self.config["workspaces"] = []
                workspace = self.fixture(name="integration intent " + str(index))
                value = self.state(workspace)
                value["tasks"]["build"]["status"] = "reviewed"
                value["integration"] = deepcopy(intent)
                dump(workspace / "state.json", value)
                before = fingerprint(workspace)
                snapshot = self.snapshot()
                feature = snapshot["features"][0]
                self.assertEqual(currency, feature["integration"]["currency"])
                self.assertEqual(intent, feature["integration"]["record"])
                self.assertEqual(currency == "current", "integrating" in feature["phases"])
                if code:
                    self.assertEqual("partial", snapshot["completeness"])
                    self.assertIn(code, {d["code"] for d in snapshot["diagnostics"]})
                else:
                    self.assertEqual("complete", snapshot["completeness"])
                self.assertEqual(before, fingerprint(workspace))

    def test_terminal_proof_repros_preserve_facts_and_cannot_clear_affected_work(self):
        cases = {c["id"]: c for c in CATALOG["cases"]}
        for identity in ("unproven-resolved-blocker", "unproven-withdrawn-feedback",
                         "unavailable-blocker-resolution", "uri-resolved-blocker",
                         "nonblocking-unproven-withdrawal", "resolved-blocker",
                         "feedback-resolved", "feedback-withdrawn", "feedback-reopened"):
            with self.subTest(case=identity):
                self.config["workspaces"] = []
                case = cases[identity]
                workspace = self.fixture(case, name="terminal " + identity)
                before = fingerprint(workspace)
                with patch("socket.socket", side_effect=AssertionError("URI metadata is never fetched")), \
                        patch("subprocess.run", side_effect=AssertionError("reader must not run commands")):
                    snapshot = self.snapshot()
                self.assert_expected(snapshot, case["expected"])
                feature = snapshot["features"][0]
                self.assertEqual("ready", feature["tasks"][0]["readiness"]["dependencies"])
                for kind in ("blockers", "feedback"):
                    for record in feature[kind]:
                        local = record["blocker_id" if kind == "blockers" else "feedback_id"]
                        source = self.state(workspace)["visibility"][kind][local]
                        self.assertEqual(source["status"], record["status"])
                        self.assertEqual(source["reason" if kind == "blockers" else "question"],
                                         record["reason" if kind == "blockers" else "question"])
                self.assertEqual(before, fingerprint(workspace))

    def test_catalog_and_manual_boundaries_cover_every_acceptance_id(self):
        criteria = {"DV-%02d" % i for i in range(1, 16)}
        seen = set()
        for case in CATALOG["cases"] + CATALOG["harness_cases"] + CATALOG["manual_evidence"]:
            self.assertTrue(case["acceptance_ids"])
            self.assertTrue(set(case["acceptance_ids"]) <= criteria)
            seen.update(case["acceptance_ids"])
        self.assertEqual(criteria, seen)
        ids = [case["id"] for case in CATALOG["cases"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_read_does_not_write_lock_mutate_execute_or_contact_network(self):
        workspace = self.fixture()
        lock = workspace / ".workflow.lock"
        lock.write_text("Synthetic held writer lock", encoding="utf-8")
        state = self.state(workspace)
        state["tasks"]["build"]["tests"] = [["never-execute-this-synthetic-command"]]
        dump(workspace / "state.json", state)
        before = fingerprint(self.root)
        runtime_before = fingerprint(SCRIPT.parent)
        original_io_open, original_os_open = io.open, os.open

        def read_only_open(file, mode="r", *args, **kwargs):
            self.assertFalse(any(flag in mode for flag in "wax+"), "Reader attempted a write")
            return original_io_open(file, mode, *args, **kwargs)

        def read_only_descriptor(file, flags, *args, **kwargs):
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            return original_os_open(file, flags, *args, **kwargs)

        with ExitStack() as stack:
            stack.enter_context(patch("builtins.open", read_only_open))
            stack.enter_context(patch("io.open", read_only_open))
            stack.enter_context(patch("os.open", read_only_descriptor))
            for method in ("mkdir", "unlink", "write_bytes", "write_text", "rename", "replace", "touch"):
                stack.enter_context(patch.object(Path, method, side_effect=AssertionError("Reader mutation: " + method)))
            for method in ("mkdir", "makedirs", "remove", "unlink", "rmdir", "rename", "replace"):
                stack.enter_context(patch.object(os, method, side_effect=AssertionError("Reader filesystem mutation: " + method)))
            stack.enter_context(patch.object(os, "system", side_effect=AssertionError("Reader shell process")))
            for method in ("run", "Popen", "check_call", "check_output"):
                stack.enter_context(patch.object(subprocess, method, side_effect=AssertionError("Reader subprocess")))
            for method in ("socket", "create_connection", "getaddrinfo"):
                stack.enter_context(patch.object(socket, method, side_effect=AssertionError("Reader network")))
            result = self.snapshot()
        self.assertEqual("complete", result["completeness"])
        self.assertEqual(before, fingerprint(self.root))
        self.assertEqual(runtime_before, fingerprint(SCRIPT.parent))
        self.assertEqual("Synthetic held writer lock", lock.read_text())

    def test_unpublished_optional_artifacts_and_targets_stay_private(self):
        original_read = Path.read_bytes
        for key in ("new-preparation", "malformed-marker", "empty-produced-tasks"):
            case = next(item for item in CATALOG["cases"] if item["id"] == key)
            with self.subTest(case=key):
                self.config["workspaces"] = []
                workspace = self.fixture(case, name=key)
                state = self.state(workspace)
                state["visibility"]["feedback"] = {
                    "hidden": dict(question="SYNTHETIC UNPUBLISHED QUESTION",
                                   artifact=dict(kind="file", target="UNPUBLISHED.txt", base="workspace", sha256=None, revision=None))
                }
                dump(workspace / "state.json", state)
                (workspace / "UNPUBLISHED.txt").write_text("SYNTHETIC UNPUBLISHED CONTENT")

                def allowed(path):
                    if path.is_relative_to(workspace):
                        self.assertEqual(workspace / "state.json", path, "Unpublished artifact was read")
                    return original_read(path)
                with patch.object(Path, "read_bytes", allowed):
                    result = self.snapshot()
                self.assertEqual([], result["features"])
                serialized = json.dumps(result)
                self.assertNotIn("UNPUBLISHED.txt", serialized)
                self.assertNotIn("SYNTHETIC UNPUBLISHED QUESTION", serialized)
                self.assertNotIn("SYNTHETIC UNPUBLISHED CONTENT", serialized)

    def test_healthy_sources_survive_root_and_workspace_failures(self):
        healthy = self.fixture()
        unsupported = next(c for c in CATALOG["cases"] if c["id"] == "unsupported-schema")
        self.fixture(unsupported, name="unsupported", identity="unsupported")
        missing = self.features / "missing"
        self.config["workspaces"].append(dict(id="missing", repository_id="repo", path=str(missing)))
        self.config["workspace_roots"] = [
            dict(id="missing-root", repository_id="repo", path=str(self.root / "missing root"))
        ]
        result = self.snapshot()
        self.assertEqual(["repo/workspace/demo"], [f["id"] for f in result["features"]])
        self.assertEqual("partial", result["completeness"])
        self.assertEqual({"MISSING_SOURCE", "UNSUPPORTED_SOURCE"}, {d["code"] for d in result["diagnostics"]})
        self.assertEqual(4, len(result["sources"]))
        self.assertEqual("available", next(s for s in result["sources"] if s["path"] == str(healthy))["status"])


    def test_explicit_identity_survives_relocation_and_overlap(self):
        workspace = self.fixture()
        self.config["workspace_roots"] = [dict(id="root", repository_id="repo", path=str(self.features))]
        first = self.snapshot()
        self.assertEqual(["repo/workspace/demo"], [f["id"] for f in first["features"]])
        before_ids = [a["id"] for a in first["features"][0]["artifacts"] if a["id"]]
        moved = self.features / "relocated feature cafÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©"
        workspace.rename(moved)
        self.config["workspaces"].append(dict(id="workspace", repository_id="repo", path=str(moved)))
        second = self.snapshot()
        self.assertEqual("complete", second["completeness"])
        self.assertEqual(first["features"][0]["id"], second["features"][0]["id"])
        self.assertEqual(before_ids, [a["id"] for a in second["features"][0]["artifacts"] if a["id"]])
        self.assertEqual(str(moved), next(s for s in second["sources"] if s["feature_id"] == "demo")["path"])

    def test_distinct_alias_collision_does_not_merge_or_hide_other_features(self):
        self.fixture()
        self.fixture(name="second existing alias", identity="workspace")
        self.fixture(name="healthy separate workspace", identity="healthy")
        result = self.snapshot()
        self.assertEqual(["repo/healthy/demo"], [f["id"] for f in result["features"]])
        self.assertIn("IDENTITY_COLLISION", {d["code"] for d in result["diagnostics"]})
        self.assertEqual("partial", result["completeness"])

    def test_same_feature_name_across_explicit_repositories_remains_distinct(self):
        self.fixture()
        other = self.fixture(name="same feature second repo", identity="other")
        self.config["workspaces"][-1].update(id="workspace", repository_id="other")
        other_repo = self.root / "second configured repository"
        other_repo.mkdir()
        self.config["repositories"].append(dict(id="other", path=str(other_repo)))
        result = self.snapshot()
        self.assertEqual(["other/workspace/demo", "repo/workspace/demo"], [f["id"] for f in result["features"]])
        self.assertEqual(str(other), result["sources"][0]["path"])

    def test_native_paths_and_explicit_foreign_path_rejection(self):
        workspace = self.fixture()
        self.assertEqual(str(workspace), self.snapshot()["sources"][0]["path"])
        bad = deepcopy(self.config)
        bad["workspaces"][0]["path"] = "/foreign/posix/workspace" if os.name == "nt" else "C:\\foreign\\workspace"
        result = self.snapshot(bad)
        self.assertEqual("unavailable", result["completeness"])
        self.assertEqual([], result["features"])
        self.assertEqual("INVALID_CONFIG", result["diagnostics"][0]["code"])

    def test_containment_rejects_repository_and_outside_artifact_reads(self):
        workspace = self.fixture()
        inside = self.repo / "private workflow"
        shutil.copytree(workspace, inside)
        config = deepcopy(self.config)
        config["workspaces"] = [dict(id="inside", repository_id="repo", path=str(inside))]
        original_read = Path.read_bytes
        def no_repository(path):
            self.assertFalse(path.is_relative_to(inside))
            return original_read(path)
        with patch.object(Path, "read_bytes", no_repository):
            result = self.snapshot(config)
        self.assertEqual([], result["features"])
        self.assertIn("ESCAPED_PATH", {d["code"] for d in result["diagnostics"]})
        outside = self.root / "outside artifact.txt"
        outside.write_text("Synthetic external content must not be read")
        state = self.state(workspace)
        state["visibility"]["control"]["evidence"].update(target=str(outside), base=None)
        dump(workspace / "state.json", state)
        def no_outside(path):
            self.assertNotEqual(outside, path)
            return original_read(path)
        with patch.object(Path, "read_bytes", no_outside):
            result = self.snapshot()
        self.assertIn("ESCAPED_PATH", {d["code"] for d in result["diagnostics"]})
        self.assertIsNone(result["features"][0]["tasks"][0]["readiness"]["start_eligible"])

    def test_permission_failure_is_not_absence_or_success(self):
        workspace = self.fixture()
        original_read = Path.read_bytes
        def denied(path):
            if path == workspace / "state.json":
                raise PermissionError("Synthetic access denial")
            return original_read(path)
        with patch.object(Path, "read_bytes", denied):
            result = self.snapshot()
        self.assertEqual([], result["features"])
        self.assertEqual("inaccessible", result["sources"][0]["status"])
        self.assertIn("INACCESSIBLE_SOURCE", {d["code"] for d in result["diagnostics"]})

    def test_concurrent_state_content_retries_without_mixed_generation(self):
        workspace = self.fixture()
        observe = reader._observe
        changed = [False]
        def concurrent_writer(path, boundary):
            value = observe(path, boundary)
            if path == workspace / "state.json" and not changed[0]:
                changed[0] = True
                state = self.state(workspace)
                state["generation"] = 2
                state["tasks"]["build"]["status"] = "implementing"
                dump(workspace / "state.json", state)
            return value
        with patch.object(reader, "_observe", concurrent_writer):
            result = self.snapshot()
        self.assertEqual(2, result["sources"][0]["generation"])
        self.assertEqual(["implementing"], result["features"][0]["phases"])

    def test_artifact_presence_changes_are_consistent_in_both_directions(self):
        for present in (False, True):
            with self.subTest(initially_present=present):
                self.config["workspaces"] = []
                workspace = self.fixture(name="presence-" + str(present))
                state = self.state(workspace)
                state["visibility"]["phases"] = [
                    dict(id="integration", phase="integrating", status="active",
                         reported_at="2026-11-06T19:00:00Z",
                         artifact=dict(kind="file", target="phase.txt", base="workspace", sha256=None, revision=None))
                ]
                dump(workspace / "state.json", state)
                target = workspace / "phase.txt"
                if not present:
                    target.unlink()
                observe, changed = reader._observe, [False]
                def concurrent_writer(path, boundary):
                    value = observe(path, boundary)
                    if path == target and not changed[0]:
                        changed[0] = True
                        if present:
                            target.unlink()
                        else:
                            target.write_text("Synthetic concurrently produced evidence")
                    return value
                with patch.object(reader, "_observe", concurrent_writer):
                    result = self.snapshot()
                self.assertEqual(not present, "integrating" in result["features"][0]["phases"])
                self.assertEqual("partial" if present else "complete", result["completeness"])

    def test_incessant_concurrent_writes_exhaust_documented_attempt_bound(self):
        workspace = self.fixture()
        config = dict(self.config, max_read_attempts=2)
        observe, reads = reader._observe, [0]
        def concurrent_writer(path, boundary):
            value = observe(path, boundary)
            if path == workspace / "state.json":
                reads[0] += 1
                if reads[0] % 2:
                    state = self.state(workspace)
                    state["generation"] += 1
                    dump(workspace / "state.json", state)
            return value
        with patch.object(reader, "_observe", concurrent_writer):
            result = self.snapshot(config)
        self.assertEqual(4, reads[0])
        self.assertEqual([], result["features"])
        self.assertEqual("inconsistent", result["sources"][0]["status"])
        self.assertIn("INCONSISTENT_READ", {d["code"] for d in result["diagnostics"]})

    @unittest.skipUnless(os.name == "nt", "Actual Windows junction capability only")
    def test_actual_windows_junction_is_rejected_without_target_reads(self):
        workspace = self.fixture()
        link = self.features / "junction alias"
        created = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(workspace)],
                                 capture_output=True, text=True)
        if created.returncode:
            self.skipTest("Windows junction unavailable: " + created.stderr)
        self.addCleanup(link.rmdir)
        config = deepcopy(self.config)
        config["workspaces"] = [dict(id="junction", repository_id="repo", path=str(link))]
        original_read = Path.read_bytes
        def no_link_read(path):
            self.assertNotIn("junction alias", str(path))
            return original_read(path)
        with patch.object(Path, "read_bytes", no_link_read):
            result = self.snapshot(config)
        self.assertEqual([], result["features"])
        self.assertIn("ESCAPED_PATH", {d["code"] for d in result["diagnostics"]})

    @unittest.skipIf(os.name == "nt", "POSIX modes are not evidence of Windows ACL enforcement")
    def test_actual_posix_read_only_workspace(self):
        workspace = self.fixture()
        for path in workspace.rglob("*"):
            path.chmod(stat.S_IRUSR | stat.S_IXUSR if path.is_dir() else stat.S_IRUSR)
        workspace.chmod(stat.S_IRUSR | stat.S_IXUSR)
        before = fingerprint(workspace)
        result = self.snapshot()
        self.assertEqual("complete", result["completeness"])
        self.assertEqual(before, fingerprint(workspace))

    def test_cli_complete_partial_and_fatal_are_json_and_nonmutating(self):
        self.fixture()
        config_path = self.root / "dashboard config.json"
        runtime_before = fingerprint(SCRIPT.parent)
        environment = dict(os.environ)
        for key in ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"):
            environment.pop(key, None)
        for mode, code in (("complete", 0), ("partial", 2), ("unavailable", 1)):
            with self.subTest(mode=mode):
                config = deepcopy(self.config)
                if mode == "partial":
                    config["workspaces"].append(dict(id="missing", repository_id="repo", path=str(self.features / "missing")))
                if mode == "unavailable":
                    config_path.write_text('{"config_version":"1.0.0","config_version":"1.0.0"}')
                else:
                    dump(config_path, config)
                before = fingerprint(self.root)
                result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(config_path)],
                                        cwd=self.root, env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(code, result.returncode, result.stderr)
                self.assertEqual("", result.stderr)
                envelope = json.loads(result.stdout)
                self.assertEqual(mode, envelope["completeness"])
                self.assertEqual(before, fingerprint(self.root))
                self.assertEqual(runtime_before, fingerprint(SCRIPT.parent))

    def test_fresh_supported_callable_import_has_no_bytecode_side_effects(self):
        self.fixture()
        runtime = self.root / "consumer runtime"
        runtime.mkdir()
        for name in ("snapshot.py", "snapshot_model.py"):
            shutil.copy2(SCRIPT.with_name(name), runtime / name)
        before = fingerprint(runtime)
        program = (
            "import sys;sys.dont_write_bytecode=True;"
            "import importlib.util,json;"
            "s=importlib.util.spec_from_file_location('fresh_snapshot',sys.argv[1]);"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
            "r=m.build_snapshot(json.loads(sys.argv[2]),now=sys.argv[3]);"
            "print(json.dumps(r['completeness']))"
        )
        result = subprocess.run([sys.executable, "-B", "-c", program, str(runtime / "snapshot.py"),
                                 json.dumps(self.config), NOW], capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('"complete"', result.stdout.strip())
        self.assertEqual(before, fingerprint(runtime))
        self.assertFalse(list(runtime.rglob("*.pyc")))



    def test_roots_do_not_recurse_or_scan_unconfigured_locations(self):
        workspace = self.fixture()
        nested = self.features / "container only" / "deep feature"
        nested.parent.mkdir()
        shutil.copytree(workspace, nested)
        outside = self.root / "unconfigured feature"
        shutil.copytree(workspace, outside)
        self.config["workspace_roots"] = [dict(id="root", repository_id="repo", path=str(self.features))]
        original = Path.read_bytes
        def bounded(path):
            self.assertFalse(path.is_relative_to(nested))
            self.assertFalse(path.is_relative_to(outside))
            return original(path)
        with patch.object(Path, "read_bytes", bounded):
            result = self.snapshot()
        self.assertEqual("complete", result["completeness"])
        self.assertEqual(["repo/workspace/demo"], [f["id"] for f in result["features"]])

    def test_malformed_sources_preserve_healthy_features_and_private_tokens(self):
        healthy = self.fixture(name="healthy", identity="healthy")
        healthy_entry = deepcopy(self.config["workspaces"][0])
        before = fingerprint(healthy)
        for case in CATALOG["cases"]:
            if case["raw_state"] is None:
                continue
            with self.subTest(case=case["id"]):
                self.config["workspaces"] = [healthy_entry]
                self.fixture(case, name=case["id"] + "-malformed", identity="bad")
                result = self.snapshot()
                self.assertEqual(["repo/healthy/demo"], [f["id"] for f in result["features"]])
                self.assertEqual("partial", result["completeness"])
                self.assertIn("MALFORMED_JSON", {d["code"] for d in result["diagnostics"]})
                self.assertNotIn("private-question", json.dumps(result))
                self.assertEqual(before, fingerprint(healthy))



    def test_invalid_or_unsupported_config_has_no_guessed_sources(self):
        for config in ({}, dict(self.config, config_version="2.0.0"), dict(self.config, max_read_attempts=0)):
            with self.subTest(config=config):
                result = self.snapshot(config)
                self.assertEqual("unavailable", result["completeness"])
                self.assertEqual([], result["sources"])
                self.assertEqual([], result["features"])
                self.assertEqual("INVALID_CONFIG", result["diagnostics"][0]["code"])


if __name__ == "__main__":
    unittest.main()
