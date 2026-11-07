"""Behavioral tests for the pure, read-only snapshot projection."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "snapshot_model", ROOT / "skills/feature-workflow/scripts/snapshot_model.py")
model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model)
NOW = "2026-11-06T20:00:00Z"
SHA = "a" * 64
HEAD = "b" * 40
AVAILABLE = {"status": "available", "reason": None}


def ref(target, **extra):
    return dict(kind="file", target=target, base="workspace", sha256=None, revision=None, **extra)


def approval(revision=1, digest=SHA):
    return dict(human="Synthetic owner", evidence="synthetic approval message", date="2026-11-06",
                revision=revision, sha256=digest)


def task(status="pending", dependencies=None, owner=None):
    return dict(status=status, depends_on=dependencies or [], owner=owner, head=HEAD, review=None)


def state(legacy=False):
    value = dict(schema_version=2, library_version="1.1.0", feature_id="sample",
                 lifecycle="active", ticket_sha256=SHA, spec_revision=1, spec_sha256=SHA,
                 spec_approval=approval(), tasks={"first": task()}, gates={},
                 integrated_head=HEAD, integration=None, pr=None, merge=None,
                 resources={}, cleanup=None, cleanup_authorization=None)
    if not legacy:
        value["visibility"] = dict(
            version="1.0.0", workspace_id="sample", eligibility=dict(
                spec_revision=1, spec_sha256=SHA, approval=approval(), task_ids=["first"],
                recorded_at="2026-11-06T19:00:00Z"),
            blockers={}, feedback={}, assignments={}, phases=[], activity=None,
            control=dict(owner_role="orchestrator", execution_authorized=True,
                         evidence=ref("decisions/execution.json")))
    return value


def statuses(**extra):
    return {"ticket.md": AVAILABLE, "specs/0001.md": AVAILABLE,
            "decisions/execution.json": AVAILABLE, **extra}


def project(value, **kw):
    options = dict(repository_id="repo", workspace_id="workspace", source_id="workspace:repo/workspace",
                   now=NOW, artifact_status=statuses())
    options.update(kw)
    return model.project_feature(value, **options)


def blocker(status="open"):
    return dict(reason="Needs configuration", resolution_condition="Record the selected value",
                blocks=["task:first"], responsible="owner", reported_by="orchestrator",
                status=status, recorded_at="2026-11-06T19:00:00Z", resolved_at=None,
                artifacts=[], history=[])


def feedback(status="open"):
    return dict(question="Which value?", artifact=ref("specs/0001.md"), requester="orchestrator",
                respondent="owner", blocks=["task:first"], blocking=True, status=status,
                recorded_at="2026-11-06T19:00:00Z", resolved_at=None, answer=None,
                disposition=None, history=[])


class SnapshotModelTests(unittest.TestCase):
    def test_projection_is_pure_and_deterministic_with_no_io(self):
        value = state()
        value["tasks"]["first"]["tests"] = [["do-not-execute", "synthetic"]]
        original, available = deepcopy(value), statuses()
        before_available = deepcopy(available)
        with patch("builtins.open", side_effect=AssertionError("file read")), \
                patch("subprocess.run", side_effect=AssertionError("process")), \
                patch("socket.socket", side_effect=AssertionError("network")), \
                patch("os.replace", side_effect=AssertionError("mutation")):
            first = project(value, artifact_status=available)
            second = project(value, artifact_status=available)
        self.assertEqual(first, second)
        self.assertEqual(original, value)
        self.assertEqual(before_available, available)
        self.assertTrue(first[0]["tasks"][0]["readiness"]["start_eligible"])

    def test_legacy_requires_actual_verified_approval_artifacts_and_tasks(self):
        value = state(legacy=True)
        self.assertIsNotNone(project(value)[0])
        self.assertIsNone(project(value, artifact_status={})[0])
        for change in ({"tasks": {}}, {"spec_approval": {}}, {"tasks": {"bad": None}}):
            bad = deepcopy(value)
            bad.update(change)
            self.assertIsNone(project(bad)[0])
        value["spec_approval"]["sha256"] = "c" * 64
        self.assertIsNone(project(value)[0])

    def test_legacy_missing_metadata_is_unavailable_not_fake_blocked_or_live(self):
        value = state(legacy=True)
        value["tasks"]["first"].update(status="implementing", owner="known-worker")
        feature, _ = project(value)
        self.assertEqual([], feature["blockers"])
        self.assertEqual("not_recorded", feature["unavailable"]["blockers"])
        assignment = feature["assignments"][0]
        self.assertEqual("known-worker", assignment["agent_id"])
        self.assertIsNone(assignment["role"])
        self.assertIsNone(assignment["last_activity"])
        self.assertEqual([], assignment["chats"])
        self.assertIsNone(feature["activity"])
        self.assertEqual("available", feature["availability"]["status"])

    def test_new_initial_preparation_is_excluded(self):
        for marker in (None, {}, [], {"task_ids": []}):
            value = state()
            value["visibility"]["eligibility"] = marker
            self.assertIsNone(project(value)[0])
        value = state()
        value["visibility"]["eligibility"]["task_ids"] = ["missing"]
        self.assertIsNone(project(value)[0])
        value = state()
        value["visibility"]["eligibility"]["approval"] = {}
        self.assertIsNone(project(value)[0])

    def test_initial_eligibility_survives_later_specification_revision(self):
        value = state()
        value.update(spec_revision=2, spec_sha256="c" * 64, spec_approval=approval(2, "c" * 64))
        feature, _ = project(value, artifact_status=statuses(**{"specs/0002.md": AVAILABLE}))
        self.assertIsNotNone(feature)
        self.assertEqual("available", feature["availability"]["status"])
        self.assertIn("repo/workspace/sample/artifact/spec%3A1",
                      [a["id"] for a in feature["artifacts"]])
        value["visibility"]["eligibility"]["approval"]["sha256"] = "d" * 64
        feature, diagnostics = project(value, artifact_status=statuses(**{"specs/0002.md": AVAILABLE}))
        self.assertIsNotNone(feature)
        self.assertEqual("partial", feature["availability"]["status"])
        self.assertIn("INVALID_APPROVAL", [d["code"] for d in diagnostics])

    def test_missing_historical_proof_does_not_invent_approval(self):
        value = state()
        feature, _ = project(value, artifact_status=statuses(**{
            "specs/0001.md": {"status": "unavailable", "reason": "missing"}}))
        self.assertIsNotNone(feature)
        self.assertEqual("partial", feature["availability"]["status"])
        self.assertIsNone(feature["tasks"][0]["readiness"]["start_eligible"])

    def test_ready_dependencies_and_recorded_authority_are_distinct(self):
        feature, _ = project(state())
        readiness = feature["tasks"][0]["readiness"]
        self.assertEqual("ready", readiness["dependencies"])
        self.assertTrue(readiness["start_eligible"])
        for control in (None, {}, {"owner_role": "planner", "execution_authorized": True}):
            value = state()
            value["visibility"]["control"] = control
            self.assertIsNone(project(value)[0]["tasks"][0]["readiness"]["start_eligible"])
        value = state()
        value["visibility"]["control"]["execution_authorized"] = False
        self.assertFalse(project(value)[0]["tasks"][0]["readiness"]["start_eligible"])

    def test_dependency_waits_name_the_existing_dependencies(self):
        value = state()
        value["tasks"]["second"] = task(dependencies=["first"])
        tasks = project(value)[0]["tasks"]
        self.assertEqual("waiting", tasks[1]["readiness"]["dependencies"])
        self.assertEqual(["first"], tasks[1]["readiness"]["waiting_on"])
        self.assertEqual([{"task_id": "first", "status": "pending"}], tasks[1]["dependency_status"])
        value["tasks"]["first"]["status"] = "complete"
        self.assertTrue(project(value)[0]["tasks"][1]["readiness"]["start_eligible"])

    def test_invalid_graphs_and_unknown_statuses_prevent_ready(self):
        variants = [
            {"first": task(dependencies=["missing"])},
            {"first": task(dependencies=["first"])},
            {"first": task(dependencies=["other"]), "other": task(dependencies=["first"])},
            {"first": task(dependencies=["other", "other"]), "other": task()},
            {"first": task(status="imaginary")},
            {"first": task(status=[])},
        ]
        for tasks in variants:
            with self.subTest(tasks=tasks):
                value = state()
                value["tasks"] = tasks
                feature, diagnostics = project(value)
                self.assertIsNotNone(feature)
                self.assertTrue(any(d["code"] == "INVALID_DEPENDENCIES" for d in diagnostics))
                self.assertFalse(any(t["readiness"]["start_eligible"] is True for t in feature["tasks"]))

    def test_lifecycle_and_concurrent_phases_do_not_assert_liveness(self):
        value = state()
        value["lifecycle"] = "published"
        value["tasks"]["first"].update(status="review", owner="worker")
        value["tasks"]["second"] = task(status="implementing")
        value["integration"] = {"phase": "prepared", "spec_revision": 1}
        feature, _ = project(value)
        self.assertEqual("published", feature["lifecycle"])
        self.assertEqual(["implementing", "integrating", "published", "under_review"], feature["phases"])
        self.assertNotIn("validating", feature["phases"])
        self.assertIsNone(feature["assignments"][0]["last_activity"])

    def test_explicit_phase_requires_actual_valid_operation_evidence(self):
        value = state()
        op = dict(id="validation", phase="validating", status="active",
                  reported_at="2026-11-06T19:00:00Z", artifact=ref("reports/validation.json"))
        value["visibility"]["phases"] = [op]
        self.assertNotIn("validating", project(value)[0]["phases"])
        feature, _ = project(value, artifact_status=statuses(**{"reports/validation.json": AVAILABLE}))
        self.assertIn("validating", feature["phases"])
        op["reported_at"] = "tomorrow"
        self.assertNotIn("validating", project(value)[0]["phases"])

    def test_explicit_blocker_preserves_resolution_condition_and_targets(self):
        value = state()
        value["visibility"]["blockers"] = {"configuration": blocker()}
        feature, _ = project(value)
        self.assertEqual("Record the selected value", feature["blockers"][0]["resolution_condition"])
        self.assertFalse(feature["tasks"][0]["readiness"]["start_eligible"])
        self.assertEqual("ready", feature["tasks"][0]["readiness"]["dependencies"])
        value["visibility"]["blockers"]["configuration"]["blocks"] = ["task:other"]
        self.assertTrue(project(value)[0]["tasks"][0]["readiness"]["start_eligible"])
        value["visibility"]["blockers"]["configuration"]["status"] = "resolved"
        feature, diagnostics = project(value)
        self.assertEqual([], feature["blockers"])
        self.assertIsNone(feature["tasks"][0]["readiness"]["start_eligible"])
        self.assertIn("INVALID_METADATA", [d["code"] for d in diagnostics])

    def test_feedback_answer_is_not_resolution_or_approval(self):
        value = state()
        question = feedback("answered")
        question["answer"] = dict(text="Value A", by="owner",
                                  recorded_at="2026-11-06T19:30:00Z", artifacts=[])
        value["visibility"]["feedback"] = {"choice": question}
        feature, _ = project(value)
        self.assertEqual("Which value?", feature["feedback"][0]["question"])
        self.assertEqual("answered", feature["feedback"][0]["status"])
        self.assertEqual("Value A", feature["feedback"][0]["answer"]["text"])
        self.assertFalse(feature["tasks"][0]["readiness"]["start_eligible"])
        self.assertEqual(approval(), value["spec_approval"])
        question["status"] = "resolved"
        question["resolved_at"] = "2026-11-06T19:40:00Z"
        question["disposition"] = dict(text="Recorded", by="orchestrator",
                                       recorded_at="2026-11-06T19:40:00Z", artifacts=[])
        feature, _ = project(value)
        self.assertTrue(feature["tasks"][0]["readiness"]["start_eligible"])

    def test_feedback_reopen_history_keeps_prior_answer(self):
        value = state()
        question = feedback()
        question["history"] = [dict(status="answered", by="owner", recorded_at=NOW,
                                    artifacts=[], answer=dict(text="Prior value", by="owner",
                                                              recorded_at=NOW, artifacts=[]))]
        value["visibility"]["feedback"] = {"choice": question}
        feature, _ = project(value)
        self.assertEqual("open", feature["feedback"][0]["status"])
        self.assertEqual("Prior value", feature["feedback"][0]["history"][0]["answer"]["text"])

    def test_activity_freshness_never_refreshes_source_timestamps(self):
        value = state()
        value["visibility"]["activity"] = dict(reported_at="2026-11-06T18:00:00Z",
            summary="Reported task work", agent_id="worker", artifact=None,
            execution=dict(status="running", observed_at="2026-11-06T18:00:00Z",
                           artifact=ref("reports/observation.json")))
        feature, _ = project(value, artifact_status=statuses(**{"reports/observation.json": AVAILABLE}))
        self.assertEqual("stale", feature["activity"]["freshness"])
        self.assertEqual("2026-11-06T18:00:00Z", feature["activity"]["reported_at"])
        self.assertEqual("running", feature["activity"]["execution"]["status"])
        self.assertEqual("2026-11-06T18:00:00Z", feature["activity"]["execution"]["observed_at"])
        value["visibility"]["activity"]["execution"]["artifact"] = None
        self.assertEqual("unknown", project(value)[0]["activity"]["execution"]["status"])

    def test_malformed_and_future_timestamps_are_explicit(self):
        for timestamp in ("2026-11-06", 0, [], "2026-11-06T22:00:00Z"):
            value = state()
            value["visibility"]["activity"] = dict(reported_at=timestamp, summary="Synthetic", agent_id=None,
                                                    artifact=None, execution=None)
            feature, diagnostics = project(value)
            self.assertEqual("invalid", feature["activity"]["freshness"])
            self.assertIn("INVALID_TIMESTAMP", [d["code"] for d in diagnostics])
            if timestamp != "2026-11-06T22:00:00Z":
                self.assertIsNone(feature["activity"]["reported_at"])
                self.assertEqual(timestamp, feature["activity"]["raw_reported_at"])

    def test_review_and_gate_currency_require_targets_integrity_and_independence(self):
        value = state()
        value["tasks"]["first"]["owner"] = "worker"
        review = dict(agent="reviewer", head=HEAD, spec_revision=1, verdict="fail", tests=["Checked"],
                      findings=[{"severity": "P2", "message": "Synthetic defect"}])
        value["tasks"]["first"]["review"] = review
        value["gates"]["validation"] = dict(agent="validator", head=HEAD, spec_revision=1,
            passed=True, evidence=["Criteria mapped"], report="reports/validation.json")
        feature, _ = project(value, artifact_status=statuses(**{"reports/validation.json": AVAILABLE}))
        self.assertEqual("current", feature["reviews"]["first"]["currency"])
        self.assertEqual("fail", feature["reviews"]["first"]["record"]["verdict"])
        self.assertEqual("current", feature["gates"]["validation"]["currency"])
        self.assertEqual("unknown", project(value)[0]["gates"]["validation"]["currency"])
        review["head"] = "c" * 40
        self.assertEqual("obsolete", project(value)[0]["reviews"]["first"]["currency"])
        review["head"], review["agent"] = HEAD, "worker"
        self.assertEqual("unknown", project(value)[0]["reviews"]["first"]["currency"])
        value["spec_approval"] = {}
        self.assertEqual("unknown", project(value)[0]["reviews"]["first"]["currency"])

    def test_publication_merge_and_cleanup_remain_separate_recorded_evidence(self):
        value = state()
        value.update(lifecycle="published", pr=dict(url="https://example.invalid/pr/1",
            head=HEAD, base="main", evidence="Recorded publication"), merge=None,
            resources={"task": {"status": "present", "path": "/synthetic/task"}},
            cleanup={"items": [{"resource_id": "task", "status": "pending", "error": "Retained"}]})
        feature, _ = project(value)
        self.assertEqual("current", feature["pr"]["currency"])
        self.assertIsNone(feature["pr"]["record"]["merge"])
        self.assertIsNone(feature["cleanup"]["record"]["cleanup_authorization"])
        self.assertEqual("present", feature["cleanup"]["record"]["resources"]["task"]["status"])
        self.assertEqual("Retained", feature["cleanup"]["record"]["cleanup"]["items"][0]["error"])

    def test_stable_artifact_identity_is_independent_of_target_and_digest_availability(self):
        def with_target(target):
            value = state()
            value["visibility"]["activity"] = dict(reported_at=NOW, summary="Report",
                agent_id=None, artifact=ref(target, artifact_id="report"), execution=None)
            return project(value, artifact_status=statuses(**{target: AVAILABLE}))[0]
        first, moved = with_target("/old/report.json"), with_target("/new/report.json")
        self.assertEqual(first["activity"]["artifact"]["id"], moved["activity"]["artifact"]["id"])
        self.assertEqual("recorded", first["activity"]["artifact"]["identity_source"])
        self.assertIn("repo/workspace/sample/artifact/ticket", [a["id"] for a in first["artifacts"]])
        value = state()
        value["visibility"]["activity"] = dict(reported_at=NOW, summary="Report",
            agent_id=None, artifact=ref("unknown.json"), execution=None)
        unknown = project(value)[0]["activity"]["artifact"]
        self.assertIsNone(unknown["id"])
        self.assertEqual("not_recorded", unknown["identity_reason"])

    def test_duplicate_artifacts_deduplicate_and_conflicts_are_not_silently_merged(self):
        value = state()
        one = ref("one.json", artifact_id="shared")
        one["sha256"] = "c" * 64
        value["visibility"]["activity"] = dict(reported_at=NOW, summary="Report",
            agent_id=None, artifact=one, execution=None)
        value["visibility"]["blockers"] = {"config": blocker()}
        value["visibility"]["blockers"]["config"]["artifacts"] = [deepcopy(one)]
        feature, _ = project(value)
        self.assertEqual(1, sum(a["id"] == "repo/workspace/sample/artifact/recorded%3Ashared"
                                for a in feature["artifacts"]))
        other = ref("two.json", artifact_id="shared")
        other["sha256"] = "d" * 64
        value["visibility"]["blockers"]["config"]["artifacts"].append(other)
        feature, diagnostics = project(value)
        self.assertIn("IDENTITY_COLLISION", [d["code"] for d in diagnostics])
        self.assertEqual("partial", feature["availability"]["status"])
        self.assertIsNone(feature["activity"]["artifact"]["id"])

    def test_invalid_optional_shapes_are_diagnostic_not_exceptions_or_success(self):
        value = state()
        value["visibility"].update(blockers=[], feedback="bad", assignments={"bad": []},
            phases=[{"id": [], "phase": [], "status": []}], activity={"reported_at": NOW,
            "artifact": {"kind": [], "target": "bad", "base": []}, "execution": {"status": []}})
        value["gates"] = []
        value["tasks"]["first"]["review"] = []
        feature, diagnostics = project(value)
        self.assertEqual("partial", feature["availability"]["status"])
        self.assertTrue(diagnostics)
        self.assertIsNone(feature["tasks"][0]["readiness"]["start_eligible"])
        self.assertEqual("unknown", feature["reviews"]["first"]["currency"])

    def test_integration_currency_uses_only_matching_recorded_evidence(self):
        value = state()
        value["integration"] = dict(task="first", phase="prepared", source_head=HEAD,
                                    parent=HEAD, spec_revision=1)
        feature, _ = project(value)
        self.assertEqual("current", feature["integration"]["currency"])
        value["integration"]["spec_revision"] = 2
        self.assertEqual("obsolete", project(value)[0]["integration"]["currency"])
        value["integration"] = None
        value["tasks"]["first"].update(status="complete", integration_commit="d" * 40,
            integration_evidence=dict(source_head=HEAD, parent="e" * 40, tree="f" * 40,
                commit="d" * 40, spec_revision=1, tests=[{"exit_code": 0}]))
        self.assertEqual("current", project(value)[0]["integration"]["currency"])
        value["tasks"]["first"]["integration_evidence"]["tests"][0]["exit_code"] = 1
        self.assertEqual("unknown", project(value)[0]["integration"]["currency"])

    def test_invalid_required_report_reference_cannot_be_current(self):
        value = state()
        report = dict(agent="validator", head=HEAD, spec_revision=1, passed=True,
                      evidence=["Mapped criteria"], report=123)
        value["gates"]["validation"] = report
        self.assertEqual("unknown", project(value)[0]["gates"]["validation"]["currency"])
        report["report"] = dict(kind="uri", target="https://example.invalid/report",
                               base=None, sha256=None, revision=None)
        feature, _ = project(value, artifact_status=statuses(**{"https://example.invalid/report": AVAILABLE}))
        self.assertEqual("unknown", feature["gates"]["validation"]["currency"])
        report["report"] = dict(kind="file", target="report.json", base=None,
                               sha256=None, revision=None)
        self.assertEqual("unknown", project(value)[0]["gates"]["validation"]["currency"])
        value["cleanup"] = []
        feature, diagnostics = project(value)
        self.assertEqual("unknown", feature["cleanup"]["currency"])
        self.assertIn("INVALID_METADATA", [d["code"] for d in diagnostics])

    def test_all_projected_entities_have_contract_required_fields(self):
        import json
        schema = json.loads((ROOT / "skills/feature-workflow/references/snapshot-schema.json").read_text())
        value = state()
        value["visibility"]["blockers"] = {"one": blocker()}
        value["visibility"]["feedback"] = {"question": feedback()}
        value["visibility"]["assignments"] = {"worker": dict(agent_id="worker", role=None,
            task_id="first", last_activity=None, chats=[])}
        feature, _ = project(value)
        self.assertTrue(set(schema["$defs"]["feature"]["required"]) <= set(feature))
        for name, rows in (("task", feature["tasks"]), ("blocker", feature["blockers"]),
                           ("feedback", feature["feedback"]), ("assignment", feature["assignments"]),
                           ("artifact", feature["artifacts"])):
            for row in rows:
                self.assertTrue(set(schema["$defs"][name]["required"]) <= set(row), name)

    def cleanup_state(self, lifecycle="closed", feature_resource=True, pending=False):
        import hashlib
        import json
        value = state()
        value["lifecycle"] = lifecycle
        value["pr"] = dict(url="https://example.invalid/pr/1", head=HEAD,
                           base="main", evidence="Recorded publication")
        if lifecycle in {"merged", "cleanup_pending", "closed"}:
            value["merge"] = dict(commit="d" * 40, head=HEAD, base="main",
                                  evidence="Recorded provider merge and local verification")
        resource = dict(kind="worktree" if feature_resource else "directory", owner="worker",
                        purpose="feature" if feature_resource else "temporary",
                        path="/synthetic/feature" if feature_resource else "/synthetic/temporary",
                        status="present" if pending else "removed",
                        branch=None, task_id=None, docker_id=None)
        if feature_resource:
            resource["branch"] = "codex/synthetic"
        value["resources"] = {"resource": resource}
        snapshot = dict(resource_id="resource", **deepcopy(resource))
        snapshot["status"] = "present"
        if feature_resource:
            snapshot["head"] = HEAD
        inventory = [snapshot]
        token = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
        value["cleanup"] = dict(inventory=inventory, inventory_sha256=token,
            items=[dict(resource_id="resource", status="pending" if pending else "removed", error=None)])
        value["cleanup_authorization"] = dict(human="Synthetic owner", evidence="Approved exact inventory",
            date="2026-11-06", feature_id="sample", inventory_sha256=token)
        return value

    def test_closed_without_required_merge_and_cleanup_proof_is_not_current(self):
        value = state()
        value.update(lifecycle="closed", resources={"feature": {"kind": "worktree", "status": "removed"}},
                     cleanup={"items": [{"resource_id": "feature", "status": "removed"}]},
                     cleanup_authorization=None, merge=None)
        feature, diagnostics = project(value)
        self.assertEqual("closed", feature["lifecycle"])
        self.assertEqual(value["cleanup"], feature["cleanup"]["record"]["cleanup"])
        self.assertEqual("unknown", feature["cleanup"]["currency"])
        self.assertEqual("partial", feature["availability"]["status"])
        self.assertTrue(diagnostics)
        self.assertIn("merge", feature["unavailable"])
        self.assertIn("cleanup.inventory", feature["unavailable"])

    def test_empty_or_mismatched_merge_proof_is_not_current_completion(self):
        value = state()
        value.update(lifecycle="merged", pr=dict(url="https://example.invalid/pr/1",
            head=HEAD, base="main", evidence="Recorded publication"), merge={})
        feature, _ = project(value)
        self.assertEqual("unknown", feature["pr"]["currency"])
        self.assertEqual("unknown", feature["cleanup"]["currency"])
        value["merge"] = dict(commit="d" * 40, head="e" * 40, base="main", evidence="Recorded merge")
        feature, _ = project(value)
        self.assertEqual("obsolete", feature["pr"]["currency"])
        self.assertEqual("obsolete", feature["cleanup"]["currency"])

    def test_legitimate_publication_and_recorded_merge_need_no_unstarted_cleanup_authorization(self):
        value = state()
        value.update(lifecycle="published", pr=dict(url="https://example.invalid/pr/1",
            head=HEAD, base="main", evidence="Recorded publication"))
        feature, _ = project(value)
        self.assertEqual("current", feature["pr"]["currency"])
        self.assertEqual("current", feature["cleanup"]["currency"])
        value.update(lifecycle="merged", merge=dict(commit="d" * 40, head=HEAD,
                     base="main", evidence={"provider": "Recorded merge", "local": "Recorded tree check"}))
        feature, _ = project(value)
        self.assertEqual("current", feature["pr"]["currency"])
        self.assertEqual("current", feature["cleanup"]["currency"])
        self.assertIsNone(feature["cleanup"]["record"]["cleanup_authorization"])

    def test_closed_requires_digest_bound_authorized_and_complete_recorded_removal(self):
        valid = self.cleanup_state()
        feature, _ = project(valid)
        self.assertEqual("current", feature["cleanup"]["currency"])
        self.assertEqual("current", feature["pr"]["currency"])
        variants = []
        value = deepcopy(valid); value["cleanup_authorization"] = None; variants.append(value)
        value = deepcopy(valid); value["cleanup_authorization"]["feature_id"] = "other"; variants.append(value)
        value = deepcopy(valid); value["cleanup_authorization"]["inventory_sha256"] = "c" * 64; variants.append(value)
        value = deepcopy(valid); value["cleanup"]["inventory_sha256"] = "c" * 64; variants.append(value)
        value = deepcopy(valid); value["cleanup"]["items"][0]["status"] = "pending"; variants.append(value)
        value = deepcopy(valid); value["cleanup"]["items"][0]["error"] = "Verification failed"; variants.append(value)
        value = deepcopy(valid); value["resources"]["resource"]["status"] = "present"; variants.append(value)
        value = deepcopy(valid); value["resources"]["resource"]["branch"] = "codex/changed"; variants.append(value)
        for value in variants:
            with self.subTest(value=value):
                feature, diagnostics = project(value)
                self.assertEqual("closed", feature["lifecycle"])
                self.assertEqual("unknown", feature["cleanup"]["currency"])
                self.assertTrue(diagnostics)

    def test_active_incremental_cleanup_and_pending_inventory_do_not_require_merge(self):
        value = self.cleanup_state(lifecycle="active", feature_resource=False)
        value["pr"] = None
        feature, _ = project(value)
        self.assertEqual("current", feature["cleanup"]["currency"])
        self.assertIsNone(feature["cleanup"]["record"]["merge"])
        import hashlib
        import json
        second = deepcopy(value["resources"]["resource"])
        second.update(status="present", path="/synthetic/retained")
        value["resources"]["retained"] = second
        value["cleanup"]["inventory"].append(dict(resource_id="retained", **deepcopy(second)))
        value["cleanup"]["items"].append(dict(resource_id="retained", status="pending", error="Retained"))
        token = hashlib.sha256(json.dumps(value["cleanup"]["inventory"], sort_keys=True).encode()).hexdigest()
        value["cleanup"]["inventory_sha256"] = token
        value["cleanup_authorization"]["inventory_sha256"] = token
        feature, _ = project(value)
        self.assertEqual("current", feature["cleanup"]["currency"])
        self.assertEqual("Retained", feature["cleanup"]["record"]["cleanup"]["items"][1]["error"])
        value = self.cleanup_state(lifecycle="active", feature_resource=False, pending=True)
        value.update(pr=None, cleanup_authorization=None)
        feature, _ = project(value)
        self.assertEqual("current", feature["cleanup"]["currency"])
        self.assertEqual("pending", feature["cleanup"]["record"]["cleanup"]["items"][0]["status"])
        self.assertIsNone(feature["cleanup"]["record"]["cleanup_authorization"])

    def test_feature_resource_removal_requires_merge_even_if_lifecycle_is_active(self):
        value = self.cleanup_state(lifecycle="active", feature_resource=True)
        feature, diagnostics = project(value)
        self.assertEqual("active", feature["lifecycle"])
        self.assertEqual("unknown", feature["cleanup"]["currency"])
        self.assertTrue(any("merge" in d["message"] for d in diagnostics))

    def test_feature_purpose_directory_and_service_cleanup_match_helper_merge_gates(self):
        import hashlib
        import json
        for kind in ("directory", "container", "network"):
            with self.subTest(kind=kind):
                value = self.cleanup_state(lifecycle="active", feature_resource=False)
                value["pr"] = None
                resource = value["resources"]["resource"]
                snapshot = value["cleanup"]["inventory"][0]
                for record in (resource, snapshot):
                    record.update(kind=kind, purpose="feature")
                    if kind in ("container", "network"):
                        record.update(path=None, docker_id="c" * 64)
                token = hashlib.sha256(json.dumps(value["cleanup"]["inventory"], sort_keys=True).encode()).hexdigest()
                value["cleanup"]["inventory_sha256"] = token
                value["cleanup_authorization"]["inventory_sha256"] = token
                feature, diagnostics = project(value)
                self.assertEqual("current", feature["cleanup"]["currency"])
                self.assertIsNone(feature["cleanup"]["record"]["merge"])
                self.assertEqual([], diagnostics)

    def earlier_task_resource(self):
        return dict(kind="worktree", owner="worker", purpose="task",
                    path="/synthetic/earlier-task", branch="codex/earlier-task",
                    task_id="first", docker_id=None, status="removed")

    def test_successive_task_then_feature_cleanup_retains_unknown_prior_proof(self):
        value = self.cleanup_state()
        value["tasks"]["first"].update(status="complete", owner="worker", head="a" * 40,
            worktree="/synthetic/earlier-task", branch="codex/earlier-task",
            integration_commit="c" * 40, integration_evidence=dict(source_head="a" * 40,
                commit="c" * 40, parent="d" * 40, tree="e" * 40, spec_revision=1,
                tests=[{"exit_code": 0}]))
        value["resources"]["earlier-task"] = self.earlier_task_resource()
        before = deepcopy(value)
        feature, diagnostics = project(value)
        self.assertEqual("closed", feature["lifecycle"])
        self.assertEqual("unknown", feature["cleanup"]["currency"])
        self.assertEqual("not_recorded", feature["unavailable"]["cleanup.prior_removal.earlier-task"])
        self.assertNotIn("cleanup.closeout", feature["unavailable"])
        self.assertFalse(any(d["code"] == "INVALID_METADATA" for d in diagnostics))
        self.assertEqual(before["resources"], feature["cleanup"]["record"]["resources"])
        self.assertEqual(before, value)

    def test_earlier_removal_does_not_require_authorizing_an_unstarted_new_inventory(self):
        value = self.cleanup_state(lifecycle="active", feature_resource=False, pending=True)
        value.update(pr=None, cleanup_authorization=None)
        value["resources"]["earlier-task"] = self.earlier_task_resource()
        feature, diagnostics = project(value)
        self.assertEqual("unknown", feature["cleanup"]["currency"])
        self.assertEqual("not_recorded", feature["unavailable"]["cleanup.prior_removal.earlier-task"])
        self.assertNotIn("cleanup_authorization", feature["unavailable"])
        self.assertFalse(any("authorization" in d["message"] for d in diagnostics))
        self.assertIsNone(feature["cleanup"]["record"]["cleanup_authorization"])

    def test_unsupported_sources_and_invalid_call_arguments(self):
        for change in ({"schema_version": 99}, {"library_version": "2.0.0"},
                       {"visibility": {"version": "2.0.0"}}, {"visibility": []}):
            value = state()
            value.update(change)
            self.assertIsNone(project(value)[0])
        self.assertIsNone(project(None)[0])
        with self.assertRaises(ValueError):
            project(state(), now=datetime(2026, 11, 6))
        with self.assertRaises(ValueError):
            project(state(), freshness_seconds=True)
        with self.assertRaises(ValueError):
            project(state(), artifact_status=[])
        feature, _ = project(state(), now=datetime(2026, 11, 6, 20, tzinfo=timezone.utc))
        self.assertIsNotNone(feature)


if __name__ == "__main__":
    unittest.main()
