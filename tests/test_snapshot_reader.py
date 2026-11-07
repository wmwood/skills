"""Filesystem and consistency behavior of the read-only snapshot interface."""
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/feature-workflow/scripts/snapshot.py"
SPEC = importlib.util.spec_from_file_location("tested_snapshot", SCRIPT)
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)
NOW = "2026-11-06T20:00:00Z"


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def hash_tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class ReaderFixture:
    def setUp(self):
        parent = Path(os.environ.get("WORKFLOW_TEST_TMP", tempfile.gettempdir())).resolve()
        self.root = parent / ("snapshot reader tests " + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(self.remove_root)
        self.repo = self.root / "original repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.features = self.root / "feature locations"
        self.features.mkdir()
        self.workspace = self.make_workspace("first feature")
        self.config = dict(config_version="1.0.0",
                           repositories=[dict(id="repo", path=str(self.repo))],
                           workspaces=[dict(id="mapped", repository_id="repo", path=str(self.workspace))])

    def remove_root(self):
        assert self.root.name.startswith("snapshot reader tests ")
        assert self.root.parent == Path(os.environ.get("WORKFLOW_TEST_TMP", tempfile.gettempdir())).resolve()
        for path in self.root.rglob("*"):
            if not path.is_symlink():
                path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        shutil.rmtree(self.root)

    def make_workspace(self, name, legacy=False, feature_id="sample"):
        root = self.features / name
        root.mkdir()
        (root / "specs").mkdir()
        (root / "ticket.md").write_bytes(b"synthetic approved scope")
        (root / "specs/0001.md").write_bytes(b"synthetic approved specification")
        ticket = hashlib.sha256((root / "ticket.md").read_bytes()).hexdigest()
        spec = hashlib.sha256((root / "specs/0001.md").read_bytes()).hexdigest()
        approval = dict(human="Synthetic human", evidence="Synthetic approval message",
                        date="2026-11-06", revision=1, sha256=spec)
        value = dict(schema_version=2, library_version="1.1.0", generation=1,
                     feature_id=feature_id, lifecycle="active", ticket_sha256=ticket,
                     spec_revision=1, spec_sha256=spec, spec_approval=approval,
                     tasks={"first": dict(status="pending", depends_on=[], owner=None, head=None, review=None)},
                     gates={}, integrated_head="b" * 40, integration=None, pr=None,
                     merge=None, resources={}, cleanup=None, cleanup_authorization=None)
        if not legacy:
            value["visibility"] = dict(version="1.0.0", workspace_id="persisted-" + feature_id,
                eligibility=dict(spec_revision=1, spec_sha256=spec, approval=deepcopy(approval),
                                 task_ids=["first"], recorded_at="2026-11-06T19:00:00Z"),
                phases=[], blockers={}, feedback={}, assignments={}, activity=None)
        dump(root / "state.json", value)
        return root

    def state(self, workspace=None):
        return json.loads(((workspace or self.workspace) / "state.json").read_text(encoding="utf-8"))

    def save(self, value, workspace=None):
        dump((workspace or self.workspace) / "state.json", value)

    def snapshot(self, config=None):
        return reader.build_snapshot(config or self.config, now=NOW)

    def explicit(self, path, identity):
        return dict(id=identity, repository_id="repo", path=str(path))

    def phase_artifact(self):
        path = self.workspace / "phase.txt"
        value = self.state()
        value["visibility"]["phases"] = [dict(id="integration-attempt", phase="integrating", status="active",
            reported_at="2026-11-06T19:00:00Z",
            artifact=dict(kind="file", target="phase.txt", base="workspace", sha256=None, revision=None))]
        self.save(value)
        return path


class SnapshotReaderTests(ReaderFixture, unittest.TestCase):
    def test_complete_deterministic_read_has_separate_unknown_authority(self):
        first = self.snapshot()
        self.assertEqual(first, self.snapshot())
        self.assertEqual("complete", first["completeness"])
        self.assertEqual("repo/mapped/sample", first["features"][0]["id"])
        self.assertEqual("ready", first["features"][0]["tasks"][0]["readiness"]["dependencies"])
        self.assertIsNone(first["features"][0]["tasks"][0]["readiness"]["start_eligible"])
        self.assertEqual("not_recorded", first["features"][0]["unavailable"]["activity"])

    def test_no_mutation_process_network_or_writer_lock_use(self):
        (self.workspace / ".workflow.lock").write_text("synthetic active writer")
        value = self.state()
        value["tasks"]["first"]["tests"] = [["must-not-execute", "synthetic"]]
        self.save(value)
        before, config = hash_tree(self.root), deepcopy(self.config)
        original_open = io.open
        def read_only(file, mode="r", *args, **kwargs):
            self.assertFalse(any(c in mode for c in "wax+"), mode)
            return original_open(file, mode, *args, **kwargs)
        with patch("io.open", side_effect=read_only), \
                patch("os.replace", side_effect=AssertionError("replace")), \
                patch("os.unlink", side_effect=AssertionError("unlink")), \
                patch("subprocess.run", side_effect=AssertionError("process")), \
                patch("subprocess.Popen", side_effect=AssertionError("process")), \
                patch("socket.socket", side_effect=AssertionError("network")):
            result = self.snapshot()
        self.assertEqual("complete", result["completeness"])
        self.assertEqual(before, hash_tree(self.root))
        self.assertEqual(config, self.config)

    def test_initial_preparation_excluded_without_draft_artifact_reads(self):
        value = self.state()
        value["tasks"] = {}
        value["visibility"]["eligibility"] = None
        value["visibility"]["feedback"] = {"private": {"question": "PRIVATE DRAFT QUESTION"}}
        self.save(value)
        paths, original = [], Path.read_bytes
        def observe(path):
            paths.append(path.name)
            return original(path)
        with patch.object(Path, "read_bytes", observe):
            result = self.snapshot()
        self.assertEqual([], result["features"])
        self.assertEqual("excluded", result["sources"][0]["status"])
        self.assertIsNone(result["sources"][0]["feature_id"])
        self.assertNotIn("ticket.md", paths)
        self.assertNotIn("PRIVATE DRAFT QUESTION", json.dumps(result))
        self.assertEqual("complete", result["completeness"])

    def test_legacy_empty_preparation_and_valid_planned_legacy(self):
        value = self.state()
        del value["visibility"]
        self.save(value)
        self.assertEqual(1, len(self.snapshot()["features"]))
        value["tasks"] = {}
        self.save(value)
        self.assertEqual("excluded", self.snapshot()["sources"][0]["status"])

    def test_roots_are_immediate_only_and_explicit_mapping_deduplicates(self):
        nested = self.features / "not a workspace"
        nested.mkdir()
        (nested / "deep").mkdir()
        dump(nested / "deep/state.json", self.state())
        config = deepcopy(self.config)
        config["workspace_roots"] = [dict(id="all", repository_id="repo", path=str(self.features))]
        result = self.snapshot(config)
        self.assertEqual(1, len(result["features"]))
        workspace = next(s for s in result["sources"] if s["workspace_id"])
        self.assertEqual(["root:all", "workspace:repo/mapped"], workspace["configured_sources"])
        self.assertEqual("mapped", workspace["workspace_id"])
        self.assertEqual("persisted-sample", workspace["recorded_workspace_id"])
        self.assertEqual(2, len(result["sources"]))

    def test_relocation_alias_identity_and_missing_alias(self):
        config = deepcopy(self.config)
        moved = self.features / "moved feature"
        config["workspaces"].append(self.explicit(moved, "mapped"))
        first = self.snapshot(config)["features"][0]["id"]
        self.workspace.rename(moved)
        second = self.snapshot(config)
        self.assertEqual(first, second["features"][0]["id"])
        self.assertEqual(1, len(second["sources"]))
        self.assertEqual("complete", second["completeness"])

    def test_distinct_existing_aliases_collide_without_hiding_healthy_work(self):
        duplicate = self.make_workspace("duplicate")
        healthy = self.make_workspace("healthy", feature_id="healthy")
        config = deepcopy(self.config)
        config["workspaces"] += [self.explicit(duplicate, "mapped"), self.explicit(healthy, "healthy")]
        result = self.snapshot(config)
        self.assertEqual(["healthy"], [f["feature_id"] for f in result["features"]])
        self.assertIn("IDENTITY_COLLISION", [d["code"] for d in result["diagnostics"]])
        self.assertEqual("partial", result["completeness"])

    def test_root_discovered_legacy_id_collision_is_not_path_identity(self):
        first = self.state()
        first.pop("visibility")
        self.save(first)
        duplicate = self.make_workspace("other", legacy=True)
        config = dict(config_version="1.0.0", repositories=self.config["repositories"],
                      workspace_roots=[dict(id="root", repository_id="repo", path=str(self.features))])
        result = self.snapshot(config)
        self.assertEqual([], result["features"])
        self.assertIn("IDENTITY_COLLISION", [d["code"] for d in result["diagnostics"]])

    def test_configuration_rejects_conflicts_types_and_non_native_paths(self):
        cases = [None, {}, {**self.config, "config_version": "2.0.0"},
                 {**self.config, "max_read_attempts": True}, {**self.config, "freshness_seconds": 0},
                 {**self.config, "workspaces": [self.explicit(Path("relative"), "x")]},
                 {**self.config, "repositories": self.config["repositories"] + [dict(id="repo", path=str(self.features))]}]
        for config in cases:
            with self.subTest(config=config):
                result = reader.build_snapshot(config, now=NOW)
                self.assertEqual("unavailable", result["completeness"])
                self.assertEqual("INVALID_CONFIG", result["diagnostics"][0]["code"])

    def test_private_locations_inside_worktree_are_not_read(self):
        inside = self.repo / "private feature"
        inside.mkdir()
        dump(inside / "state.json", self.state())
        config = deepcopy(self.config)
        config["workspaces"] = [self.explicit(inside, "inside")]
        result = self.snapshot(config)
        self.assertEqual([], result["features"])
        self.assertEqual("ESCAPED_PATH", result["diagnostics"][0]["code"])

    def test_malformed_duplicate_and_nonfinite_sources_do_not_hide_healthy(self):
        bad = self.make_workspace("bad")
        config = deepcopy(self.config)
        config["workspaces"].append(self.explicit(bad, "bad"))
        for raw in ('{"tasks":', '{"schema_version":2,"schema_version":2}',
                    '{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}', '{"value":1e999}'):
            (bad / "state.json").write_text(raw)
            result = self.snapshot(config)
            self.assertEqual(1, len(result["features"]))
            self.assertEqual("partial", result["completeness"])
            self.assertIn("MALFORMED_JSON", [d["code"] for d in result["diagnostics"]])

    def test_unsupported_missing_and_inaccessible_sources_are_explicit(self):
        bad = self.make_workspace("unsupported")
        value = self.state(bad)
        value["schema_version"] = 999
        self.save(value, bad)
        missing = self.features / "missing"
        config = deepcopy(self.config)
        config["workspaces"] += [self.explicit(bad, "bad"), self.explicit(missing, "missing")]
        original = Path.read_bytes
        def denied(path):
            if path == self.workspace / "state.json":
                raise PermissionError(13, "synthetic permission failure")
            return original(path)
        with patch.object(Path, "read_bytes", denied):
            result = self.snapshot(config)
        self.assertEqual({"inaccessible", "unsupported", "missing"}, {s["status"] for s in result["sources"]})
        self.assertEqual("partial", result["completeness"])

    def test_missing_and_digest_mismatch_artifacts_never_verify_approval(self):
        (self.workspace / "specs/0001.md").write_bytes(b"changed without approval")
        self.assertEqual("partial", self.snapshot()["features"][0]["availability"]["status"])
        value = self.state()
        value["visibility"]["eligibility"]["approval"]["date"] = "invalid"
        self.save(value)
        (self.workspace / "ticket.md").unlink()
        result = self.snapshot()
        self.assertEqual(1, len(result["features"]))  # Structurally historical marker remains diagnostic/partial.
        self.assertEqual("partial", result["features"][0]["availability"]["status"])
        self.assertIn("INVALID_APPROVAL", [d["code"] for d in result["diagnostics"]])

    def test_unsafe_artifact_reference_is_metadata_only_not_read(self):
        outside = self.root / "outside-secret.txt"
        outside.write_bytes(b"must not read")
        value = self.state()
        value["visibility"]["control"] = dict(owner_role="orchestrator", execution_authorized=True,
            evidence=dict(kind="file", target=str(outside), base=None, sha256=None, revision=None))
        self.save(value)
        original = Path.read_bytes
        def checked(path):
            self.assertNotEqual(outside, path)
            return original(path)
        with patch.object(Path, "read_bytes", checked):
            result = self.snapshot()
        self.assertIn("ESCAPED_PATH", [d["code"] for d in result["diagnostics"]])
        self.assertIsNone(result["features"][0]["tasks"][0]["readiness"]["start_eligible"])

    def test_invalid_artifact_target_diagnoses_without_filesystem_exception(self):
        value = self.state()
        value["visibility"]["control"] = dict(owner_role="orchestrator", execution_authorized=True,
            evidence=dict(kind="file", target="bad" + chr(0) + "path", base="workspace", sha256=None, revision=None))
        self.save(value)
        result = self.snapshot()
        self.assertEqual("partial", result["completeness"])
        self.assertIn("INVALID_METADATA", [d["code"] for d in result["diagnostics"]])
        self.assertIsNone(result["features"][0]["tasks"][0]["readiness"]["start_eligible"])

    def test_changed_state_retries_whole_source_then_projects_one_generation(self):
        original = reader._observe
        changed = False
        def racing(path, boundary):
            nonlocal changed
            observation = original(path, boundary)
            if path == self.workspace / "state.json" and not changed:
                changed = True
                value = self.state()
                value["generation"] = 2
                value["tasks"]["first"]["status"] = "implementing"
                self.save(value)
            return observation
        with patch.object(reader, "_observe", racing):
            result = self.snapshot()
        self.assertEqual(2, result["sources"][0]["generation"])
        self.assertEqual(["implementing"], result["features"][0]["phases"])

    def test_artifact_presence_transitions_are_rechecked_both_directions(self):
        for initially_exists in (True, False):
            with self.subTest(initially_exists=initially_exists):
                path = self.phase_artifact()
                if initially_exists:
                    path.write_bytes(b"phase evidence")
                elif path.exists():
                    path.unlink()
                original, changed = reader._observe, [False]
                def racing(target, boundary):
                    observation = original(target, boundary)
                    if target == path and not changed[0]:
                        changed[0] = True
                        if initially_exists:
                            path.unlink()
                        else:
                            path.write_bytes(b"phase evidence")
                    return observation
                with patch.object(reader, "_observe", racing):
                    result = self.snapshot()
                self.assertEqual(not initially_exists, "integrating" in result["features"][0]["phases"])
                self.assertEqual("partial" if initially_exists else "complete", result["completeness"])

    def test_malformed_typed_provenance_normalizes_without_hiding_healthy_source(self):
        healthy = self.make_workspace("healthy provenance", feature_id="healthy")
        config = deepcopy(self.config)
        config["workspaces"].append(self.explicit(healthy, "healthy"))
        original = self.state()
        cases = [(field, value) for field in ("schema_version", "generation")
                 for value in (-1, True, 1.5, "wrong", [], {})]
        cases += [(field, value) for field in ("library_version", "feature_id")
                  for value in (True, 12, [], {})]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                malformed = deepcopy(original)
                malformed[field] = value
                self.save(malformed)
                result = self.snapshot(config)
                self.assertIn("healthy", [f["feature_id"] for f in result["features"]])
                source = next(v for v in result["sources"] if v["workspace_id"] == "mapped")
                self.assertIsNone(source[field])
                self.assertIn("INVALID_SOURCE", [d["code"] for d in source["diagnostics"]])
                for observed in result["sources"]:
                    for number in ("schema_version", "generation"):
                        self.assertTrue(observed[number] is None or
                                        type(observed[number]) is int and observed[number] >= 0)
                    for text in ("library_version", "feature_id"):
                        self.assertTrue(observed[text] is None or isinstance(observed[text], str))

    def test_invalid_initial_marker_or_task_production_cannot_read_or_leak_drafts(self):
        private_name, private_content = "PRIVATE DRAFT QUESTION.txt", "PRIVATE DRAFT CONTENT"
        (self.workspace / private_name).write_text(private_content)
        healthy = self.make_workspace("healthy privacy", feature_id="healthy")
        config = deepcopy(self.config)
        config["workspaces"].append(self.explicit(healthy, "healthy"))
        original = self.state()
        marker = original["visibility"]["eligibility"]
        cases = [({}, {}), ([], marker), (None, marker), ({"first": None}, marker),
                 (original["tasks"], {}), (original["tasks"], []),
                 (original["tasks"], {**marker, "task_ids": []}),
                 (original["tasks"], {**marker, "task_ids": ["not-produced"]}),
                 (original["tasks"], {**marker, "recorded_at": "not-a-time"}),
                 (original["tasks"], {**marker, "recorded_at": "9999-12-31T23:59:59-23:59"}),
                 (original["tasks"], None)]
        original_read = Path.read_bytes
        for tasks, eligibility in cases:
            with self.subTest(tasks=tasks, eligibility=eligibility):
                value = deepcopy(original)
                value["tasks"] = deepcopy(tasks)
                value["visibility"]["eligibility"] = deepcopy(eligibility)
                value["visibility"]["feedback"] = {"private": dict(
                    question="PRIVATE DRAFT QUESTION",
                    artifact=dict(kind="file", target=private_name, base="workspace", sha256=None, revision=None))}
                self.save(value)
                def allowed(path):
                    if path.is_relative_to(self.workspace):
                        self.assertEqual(self.workspace / "state.json", path,
                                         "An unpublished artifact was read")
                    return original_read(path)
                with patch.object(Path, "read_bytes", allowed):
                    result = self.snapshot(config)
                self.assertEqual(["healthy"], [f["feature_id"] for f in result["features"]])
                self.assertNotIn(private_name, json.dumps(result))
                self.assertNotIn(private_content, json.dumps(result))
                source = next(v for v in result["sources"] if v["workspace_id"] == "mapped")
                self.assertIsNone(source["feature_id"])

    def test_legacy_optional_reports_wait_for_canonical_approval_integrity(self):
        private_name = "PRIVATE LEGACY DRAFT REPORT.txt"
        (self.workspace / private_name).write_text("PRIVATE LEGACY CONTENT")
        original = self.state()
        original.pop("visibility")
        original["tasks"]["first"]["review"] = dict(report=private_name)
        for kind in ("invalid-date", "wrong-binding", "bad-file-digest"):
            with self.subTest(kind=kind):
                value = deepcopy(original)
                (self.workspace / "specs/0001.md").write_bytes(b"synthetic approved specification")
                if kind == "invalid-date":
                    value["spec_approval"]["date"] = "not-an-approval-date"
                elif kind == "wrong-binding":
                    value["spec_approval"]["sha256"] = "f" * 64
                else:
                    (self.workspace / "specs/0001.md").write_bytes(b"unapproved replacement")
                self.save(value)
                original_read = Path.read_bytes
                def allowed(path):
                    self.assertNotEqual(self.workspace / private_name, path)
                    return original_read(path)
                with patch.object(Path, "read_bytes", allowed):
                    result = self.snapshot()
                self.assertEqual([], result["features"])
                self.assertNotIn(private_name, json.dumps(result))
                self.assertNotIn("PRIVATE LEGACY CONTENT", json.dumps(result))
                self.assertIsNone(result["sources"][0]["feature_id"])

    def test_malformed_json_diagnostics_do_not_echo_private_duplicate_keys(self):
        (self.workspace / "state.json").write_text(
            '{"PRIVATE DRAFT QUESTION":0,"PRIVATE DRAFT QUESTION":1}')
        result = self.snapshot()
        self.assertIn("MALFORMED_JSON", [d["code"] for d in result["diagnostics"]])
        self.assertNotIn("PRIVATE DRAFT QUESTION", json.dumps(result))

    def test_repeated_races_exhaust_bounded_attempts_without_mixed_result(self):
        config = {**self.config, "max_read_attempts": 2}
        original, count = reader._observe, [0]
        def racing(path, boundary):
            result = original(path, boundary)
            if path == self.workspace / "state.json":
                count[0] += 1
                if count[0] % 2:
                    value = self.state()
                    value["generation"] += 1
                    self.save(value)
            return result
        with patch.object(reader, "_observe", racing):
            result = self.snapshot(config)
        self.assertEqual(4, count[0])
        self.assertEqual([], result["features"])
        self.assertEqual("inconsistent", result["sources"][0]["status"])

    def test_reparse_or_symlink_escape_is_not_followed(self):
        link = self.features / "linked feature"
        try:
            link.symlink_to(self.workspace, target_is_directory=True)
        except OSError as error:
            self.skipTest("OS does not permit directory symlinks: " + str(error))
        config = deepcopy(self.config)
        config["workspaces"] = [self.explicit(link, "link")]
        original = Path.read_bytes
        def checked(path):
            self.assertNotIn("linked feature", str(path))
            return original(path)
        with patch.object(Path, "read_bytes", checked):
            result = self.snapshot(config)
        self.assertEqual("ESCAPED_PATH", result["diagnostics"][0]["code"])
        self.assertEqual([], result["features"])

    def test_root_discovery_classifies_invalid_shapes_without_inventing_identity(self):
        config = dict(config_version="1.0.0", repositories=self.config["repositories"],
                      workspace_roots=[dict(id="root", repository_id="repo", path=str(self.features))])
        for value, code in (([], "INVALID_SOURCE"), ({"schema_version": 999}, "UNSUPPORTED_SOURCE"),
                            ({**self.state(), "visibility": []}, "INVALID_METADATA")):
            self.save(value)
            result = self.snapshot(config)
            self.assertEqual([], result["features"])
            self.assertIn(code, [d["code"] for d in result["diagnostics"]])

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_windows_junction_entry_is_rejected_without_reading_target(self):
        link = self.features / "junction feature"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.workspace)],
                                capture_output=True, text=True)
        if result.returncode:
            self.skipTest("Junction creation unavailable: " + result.stderr)
        self.addCleanup(link.rmdir)
        config = deepcopy(self.config)
        config["workspaces"] = [self.explicit(link, "junction")]
        original = Path.read_bytes
        def checked(path):
            self.assertNotIn("junction feature", str(path))
            return original(path)
        with patch.object(Path, "read_bytes", checked):
            snapshot = self.snapshot(config)
        self.assertEqual([], snapshot["features"])
        self.assertIn("ESCAPED_PATH", [d["code"] for d in snapshot["diagnostics"]])

    @unittest.skipIf(os.name == "nt", "POSIX mode enforcement is not Windows ACL evidence")
    def test_real_read_only_workspace_is_readable(self):
        for path in self.workspace.rglob("*"):
            path.chmod(0o555 if path.is_dir() else 0o444)
        self.workspace.chmod(0o555)
        self.assertEqual("complete", self.snapshot()["completeness"])


if __name__ == "__main__":
    unittest.main()
