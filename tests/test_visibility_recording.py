"""Visibility writer tests use disposable workflow fixtures, never live state."""
import copy
from datetime import date
import re
import json
import subprocess
import sys
import unittest
from unittest import mock

import test_workflow as fixtures

workflow = fixtures.workflow


class VisibilityRecordingTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    remove_test_directory = fixtures.WorkflowTests.remove_test_directory
    git = fixtures.WorkflowTests.git
    def invoke(self, method, writer_role="orchestrator", **arguments):
        with workflow.Workspace(self.path, "coordinator-session", writer_role).transaction() as workspace:
            return getattr(workspace, method)(**arguments)

    read = fixtures.WorkflowTests.read
    def add(self, task="first", dependencies=None):
        self.invoke("add_task", writer_role="planner", task_id=task,
                    depends_on=dependencies or [], scope=[task + ".txt"],
                    acceptance_ids=["AC1"], tests=[["python", "--version"]])

    def proof(self):
        return dict(kind="uri", target="codex://test-chat/message-1", base=None,
                    sha256=None, revision=None, artifact_id="approval-evidence")

    def adopt(self):
        return self.invoke("adopt_visibility", workspace_id="stable-workspace",
                           quiescent=True, evidence=self.proof())

    def publish(self):
        self.add()
        self.adopt()

    def feedback(self, status="open", **changes):
        values = dict(feedback_id="product-question", question="Which behavior is approved?",
                      artifact=self.proof(), blocks=["task:first"], blocking=True,
                      respondent="test human", status=status)
        values.update(changes)
        return self.invoke("record_feedback", **values)

    def response(self, text):
        return dict(text=text, by="test human", recorded_at="2026-11-06T20:00:00Z",
                    artifacts=[self.proof()])

    def test_existing_workspaces_are_not_adopted_by_other_operations(self):
        self.add()
        self.assertNotIn("visibility", self.read())
        before = (self.path / "state.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "adoption"):
            self.invoke("record_activity", activity={})
        self.assertEqual(before, (self.path / "state.json").read_bytes())

    def test_new_workspace_metadata_is_opt_in_and_unpublished(self):
        other = self.root / "new visible workspace"
        state = workflow.initialize(self.repo, other, "new-feature", self.ticket,
            self.specification, self.approved, workspace_id="durable-id")
        self.assertEqual(state["visibility"]["workspace_id"], "durable-id")
        self.assertIsNone(state["visibility"]["eligibility"])
        self.assertIsNone(state["visibility"]["activity"])
        self.assertEqual(state["schema_version"], 2)

    def test_adoption_backups_and_immediate_rollback_preserve_history(self):
        before = self.read()
        with self.assertRaisesRegex(ValueError, "quiescence"):
            self.invoke("adopt_visibility", workspace_id="durable", quiescent=False,
                        evidence=self.proof())
        record = self.adopt()
        backup = self.path / record["backup"]
        self.assertEqual(json.loads(backup.read_text()), before)
        self.assertEqual(workflow.digest(backup), record["sha256"])
        current = self.read()
        self.assertNotIn("activity", current["visibility"])
        self.assertIsNone(current["visibility"]["eligibility"])
        workflow.reported_time(record["recorded_at"])
        self.invoke("rollback_visibility", backup=record["backup"],
                    backup_sha256=record["sha256"],
                    current_sha256=workflow.digest(self.path / "state.json"),
                    quiescent=True, evidence=self.proof())
        after = self.read()
        self.assertNotIn("visibility", after)
        self.assertEqual(after["generation"], before["generation"] + 2)
        self.assertTrue(backup.exists())
        self.assertTrue(list((self.path / "reports").glob("visibility-rollback-*.json")))

    def test_adoption_preserves_known_legacy_eligibility_without_inventing_history(self):
        self.add()
        approved = copy.deepcopy(self.read()["spec_approval"])
        self.adopt()
        value = self.read()["visibility"]
        self.assertEqual(value["eligibility"]["approval"], approved)
        self.assertEqual(value["eligibility"]["task_ids"], ["first"])
        self.assertEqual(value["eligibility"]["recorded_at"][:10], value["adoption"]["recorded_at"][:10])
        for field in ("phases", "blockers", "feedback", "assignments", "activity"):
            self.assertNotIn(field, value)
        self.invoke("record_blocker", blocker_id="new-report", reason="Actual current blocker",
                    resolution_condition="Provide evidence", blocks=["feature"])
        self.assertEqual(set(self.read()["visibility"]["blockers"]), {"new-report"})
        self.assertNotIn("activity", self.read()["visibility"])

    def test_adoption_report_failure_never_persists_partial_visibility(self):
        self.add()
        before = (self.path / "state.json").read_bytes()
        with mock.patch.object(workflow.Workspace, "save_report", side_effect=ValueError("Report exists")):
            with self.assertRaisesRegex(ValueError, "Report exists"):
                self.adopt()
        self.assertEqual(before, (self.path / "state.json").read_bytes())
        self.assertNotIn("visibility", self.read())
        self.assertTrue(list((self.path / "backups").glob("visibility-*.json")))

    def test_invalid_legacy_graph_is_not_published_during_adoption(self):
        self.add()
        state = self.read()
        state["tasks"]["first"]["depends_on"] = ["absent"]
        workflow.atomic_json(self.path / "state.json", state)
        self.adopt()
        value = self.read()["visibility"]
        self.assertIsNone(value["eligibility"])
        self.assertEqual(value["adoption"]["legacy_eligibility"], "not_verified")
        self.assertNotIn("blockers", value)

    def test_unknown_metadata_version_and_worker_adoption_are_rejected(self):
        with self.assertRaises(ValueError):
            self.invoke("adopt_visibility", writer_role="implementer", workspace_id="unknown",
                        quiescent=True, evidence=self.proof())
        self.adopt()
        state = self.read()
        state["visibility"]["version"] = "99.0.0"
        workflow.atomic_json(self.path / "state.json", state)
        before = (self.path / "state.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "Incompatible visibility"):
            self.invoke("record_control", execution_authorized=True, evidence=self.proof())
        self.assertEqual(before, (self.path / "state.json").read_bytes())

    def test_rollback_refuses_intervening_changes_or_wrong_digest(self):
        record = self.adopt()
        with self.assertRaisesRegex(ValueError, "Current state"):
            self.invoke("rollback_visibility", backup=record["backup"],
                backup_sha256=record["sha256"], current_sha256="0" * 64,
                quiescent=True, evidence=self.proof())
        self.add()
        before = (self.path / "state.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "Intervening"):
            self.invoke("rollback_visibility", backup=record["backup"],
                backup_sha256=record["sha256"],
                current_sha256=workflow.digest(self.path / "state.json"),
                quiescent=True, evidence=self.proof())
        self.assertEqual(before, (self.path / "state.json").read_bytes())

    def test_publication_requires_tasks_and_keeps_initial_approval_after_revision(self):
        self.adopt()
        with self.assertRaisesRegex(ValueError, "Produced tasks"):
            self.invoke("publish_visibility")
        self.add()
        self.invoke("publish_visibility", task_ids=["first"])
        initial = copy.deepcopy(self.read()["visibility"]["eligibility"])
        self.assertEqual(initial["approval"]["date"], self.approved["date"])
        self.assertEqual(initial["task_ids"], ["first"])
        revision = self.root / "revised specification.md"
        revision.write_text("AC1: revised approved behavior.\n")
        self.invoke("revise", spec=str(revision), approved=self.approved,
                    affected_tasks=["first"])
        self.assertEqual(self.read()["spec_revision"], 2)
        self.assertEqual(self.read()["visibility"]["eligibility"], initial)
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.invoke("publish_visibility")

    def test_publication_rejects_invalid_task_graph(self):
        self.adopt()
        self.add()
        state = self.read()
        state["tasks"]["first"]["depends_on"] = ["first"]
        workflow.atomic_json(self.path / "state.json", state)
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            self.invoke("publish_visibility")
        self.assertIsNone(self.read()["visibility"]["eligibility"])

    def test_owner_handoff_blocks_planner_impersonation_and_other_writers(self):
        self.adopt()
        with self.assertRaises(ValueError):
            self.invoke("record_control", writer_role="planner", execution_authorized=True,
                        evidence=self.proof())
        with self.assertRaises(ValueError):
            self.invoke("record_control", writer_role="implementer", execution_authorized=True,
                        evidence=self.proof())
        self.invoke("record_control", execution_authorized=True, evidence=self.proof())
        for operation, args in (
            ("record_control", dict(execution_authorized=False, evidence=self.proof())),
            ("add_task", dict(task_id="new", depends_on=[], scope=["new"], acceptance_ids=["AC1"],
                              tests=[["python", "--version"]]))):
            with self.assertRaisesRegex(ValueError, "handed"):
                self.invoke(operation, writer_role="planner", **args)
        self.assertEqual(self.read()["visibility"]["control"]["owner_role"], "orchestrator")

    def test_blocker_resolution_needs_evidence_and_preserves_reopening_history(self):
        self.publish()
        fields = dict(blocker_id="blocked-api", reason="API contract missing",
                      resolution_condition="Owner supplies reviewed contract", blocks=["task:first"])
        self.invoke("record_blocker", **fields)
        with self.assertRaisesRegex(ValueError, "Resolution evidence"):
            self.invoke("record_blocker", **fields, status="resolved")
        self.invoke("record_blocker", **fields, status="resolved", artifacts=[self.proof()])
        self.invoke("record_blocker", **fields, status="open")
        record = self.read()["visibility"]["blockers"]["blocked-api"]
        self.assertEqual([h["status"] for h in record["history"]], ["open", "resolved", "open"])
        self.assertIsNone(record["resolved_at"])
        self.assertEqual(self.read()["tasks"]["first"]["status"], "pending")
        with self.assertRaisesRegex(ValueError, "Unknown visibility target"):
            self.invoke("record_blocker", **dict(fields, blocker_id="unknown", blocks=["task:absent"]))

    def test_feedback_answer_resolution_and_reopening_do_not_approve_specification(self):
        self.publish()
        approval = copy.deepcopy(self.read()["spec_approval"])
        self.feedback()
        with self.assertRaisesRegex(ValueError, "answer evidence"):
            self.feedback(status="answered")
        self.feedback(status="answered", answer=self.response("Use the existing behavior"))
        self.feedback(status="resolved", disposition=self.response("Recorded in a proposed revision"))
        self.feedback(status="open")
        record = self.read()["visibility"]["feedback"]["product-question"]
        self.assertEqual([h["status"] for h in record["history"]],
                         ["open", "answered", "resolved", "open"])
        self.assertEqual(record["history"][2]["previous_answer"]["text"], "Use the existing behavior")
        self.assertEqual(self.read()["spec_approval"], approval)
        self.assertEqual(self.read()["spec_revision"], 1)

    def test_phases_require_publication_and_explicit_report_evidence(self):
        self.adopt()
        args = dict(operation_id="integration-1", phase="integrating", status="active",
                    reported_at="2026-11-06T20:00:00Z", artifact=self.proof())
        with self.assertRaisesRegex(ValueError, "publication"):
            self.invoke("record_phase", **args)
        self.add()
        self.invoke("publish_visibility")
        self.invoke("record_phase", **args)
        self.invoke("record_phase", **dict(args, status="finished"))
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.invoke("record_phase", **args)
        self.assertEqual(self.read()["visibility"]["phases"][0]["status"], "finished")

    def test_activity_and_assignment_do_not_infer_liveness_or_change_task_owner(self):
        self.publish()
        activity = dict(reported_at="2026-11-06T20:00:00Z", summary="Submitted report",
                        agent_id="known-agent", artifact=self.proof(), execution=None)
        self.invoke("record_assignment", assignment_id="implementer-first", agent_id="known-agent",
            role="feature-implementer", task_id="first", last_activity=activity,
            chats=[dict(provider="codex", id="actual-chat", uri=None)])
        self.invoke("record_activity", activity=activity)
        state = self.read()
        self.assertIsNone(state["visibility"]["activity"]["execution"])
        self.assertIsNone(state["tasks"]["first"]["owner"])
        self.assertIsNone(state["visibility"]["assignments"]["implementer-first"]["chats"][0]["uri"])
        bad = dict(activity, execution=dict(status="running", observed_at=None, artifact=None))
        with self.assertRaisesRegex(ValueError, "observation time"):
            self.invoke("record_activity", activity=bad)
        self.assertIsNone(self.read()["visibility"]["activity"]["execution"])

    def test_cli_typed_operations_keep_writer_role_separate_from_assignment_role(self):
        request = self.root / "visibility request with spaces.json"
        helper = fixtures.HELPER
        def cli(operation, payload, writer="orchestrator"):
            request.write_text(json.dumps(payload), encoding="utf-8-sig")
            result = subprocess.run([sys.executable, str(helper), operation,
                "--workspace", str(self.path), "--request", str(request),
                "--actor", "cli-owner", "--role", writer], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        cli("adopt-visibility", dict(workspace_id="stable-workspace", quiescent=True,
                                     evidence=self.proof()), writer="planner")
        self.add()
        cli("publish-visibility", {}, writer="planner")
        cli("record-assignment", dict(assignment_id="cli-worker", agent_id="known-session",
            role="feature-implementer", task_id="first", chats=[]))
        value = self.read()["visibility"]
        self.assertEqual(value["assignments"]["cli-worker"]["role"], "feature-implementer")
        self.assertEqual(value["eligibility"]["task_ids"], ["first"])
        self.assertIsNone(self.read()["tasks"]["first"]["owner"])

    def test_new_artifact_identity_matches_the_consumer_identity_grammar(self):
        self.adopt()
        for bad_id in ("not/a/stable id", "contains space", "", "a" * 129, None, 7, "Ã©vidence"):
            before = (self.path / "state.json").read_bytes()
            ref = dict(self.proof(), artifact_id=bad_id)
            with self.assertRaisesRegex(ValueError, "visibility ID"):
                self.invoke("record_control", execution_authorized=True, evidence=ref)
            self.assertEqual(before, (self.path / "state.json").read_bytes())
        valid_id = "Artifact-ID_42.v1"
        self.invoke("record_control", execution_authorized=True,
                    evidence=dict(self.proof(), artifact_id=valid_id))
        actual = self.read()["visibility"]["control"]["evidence"]["artifact_id"]
        self.assertEqual(actual, valid_id)
        self.assertIsNotNone(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", actual))

    def test_publication_accepts_only_projectable_calendar_approval_dates(self):
        self.adopt()
        self.add()
        for bad_date in ("2026-11-06T20:00:00Z", "2026-02-30", "2026-11-6", "20261106", "yesterday",
                         "２０２６-11-06", "٢٠٢٦-11-06", "2026-１１-06", "2026-11-٠٦"):
            state = self.read()
            state["spec_approval"]["date"] = bad_date
            workflow.atomic_json(self.path / "state.json", state)
            before = (self.path / "state.json").read_bytes()
            with self.assertRaises(ValueError):
                self.invoke("publish_visibility")
            self.assertEqual(before, (self.path / "state.json").read_bytes())
            self.assertIsNone(self.read()["visibility"]["eligibility"])
            self.assertEqual(self.read()["spec_approval"]["date"], bad_date)
        state = self.read()
        state["spec_approval"]["date"] = "2026-11-06"
        workflow.atomic_json(self.path / "state.json", state)
        self.invoke("publish_visibility")
        actual = self.read()["visibility"]["eligibility"]["approval"]["date"]
        self.assertEqual(actual, "2026-11-06")
        self.assertEqual(date.fromisoformat(actual).isoformat(), actual)

    def test_adoption_preserves_but_does_not_publish_timestamp_form_approval(self):
        self.add()
        state = self.read()
        original_date = "2026-11-06T20:00:00Z"
        state["spec_approval"]["date"] = original_date
        workflow.atomic_json(self.path / "state.json", state)
        self.adopt()
        state = self.read()
        self.assertIsNone(state["visibility"]["eligibility"])
        self.assertEqual(state["visibility"]["adoption"]["legacy_eligibility"], "not_verified")
        self.assertEqual(state["spec_approval"]["date"], original_date)

    def test_adoption_preserves_unicode_approval_date_without_verified_eligibility(self):
        self.add()
        state = self.read()
        original_date = "２０２６-11-06"
        state["spec_approval"]["date"] = original_date
        workflow.atomic_json(self.path / "state.json", state)
        self.adopt()
        state = self.read()
        self.assertIsNone(state["visibility"]["eligibility"])
        self.assertEqual(state["visibility"]["adoption"]["legacy_eligibility"], "not_verified")
        self.assertEqual(state["spec_approval"]["date"], original_date)

    def test_artifact_containment_digest_and_timestamp_validation(self):
        self.publish()
        outside = dict(kind="file", target=str(self.ticket), base=None, sha256=None, revision=None)
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.invoke("record_control", execution_authorized=True, evidence=outside)
        artifact = self.path / "local evidence.txt"
        artifact.write_text("real evidence")
        ref = dict(kind="file", target="local evidence.txt", base="workspace",
                   sha256="0" * 64, revision=None)
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.invoke("record_control", execution_authorized=True, evidence=ref)
        ref["sha256"] = workflow.digest(artifact)
        self.invoke("record_control", execution_authorized=True, evidence=ref)
        for value in ("2026-11-06", "2026-11-06T12:00:00", "2026-99-06T12:00:00Z"):
            with self.assertRaises(ValueError):
                self.invoke("record_activity", activity=dict(reported_at=value, summary="Report",
                    agent_id=None, artifact=None, execution=None))


if __name__ == "__main__":
    unittest.main()
