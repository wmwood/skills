"""Integration tests use disposable local Git repositories; no network or live checkout edits."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import stat
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "skills/feature-workflow/scripts/workflow.py"
SPEC = importlib.util.spec_from_file_location("workflow", HELPER)
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        # mkdtemp's private 0700 directory ACL is inaccessible to child processes
        # in some Windows sandboxes. Ordinary mkdir inherits the allowed root ACL.
        self.temporary_parent = Path(os.environ.get("WORKFLOW_TEST_TMP", tempfile.gettempdir())).resolve()
        self.root = self.temporary_parent / (
            "feature workflow tests " + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(self.remove_test_directory)
        self.repo = self.root / "original repo"
        self.repo.mkdir()
        self.git(self.repo, "init", "-b", "main")
        self.git(self.repo, "config", "user.name", "Workflow Test")
        self.git(self.repo, "config", "user.email", "workflow@example.invalid")
        self.git(self.repo, "config", "commit.gpgsign", "false")
        for name in ("AGENTS.md", "GLOSSARY.md", "tracked.txt"):
            (self.repo / name).write_text("baseline\n", encoding="utf-8")
        self.git(self.repo, "add", ".")
        self.git(self.repo, "commit", "-m", "baseline")
        self.ticket = self.root / "ticket input.md"
        self.specification = self.root / "spec input.md"
        self.ticket.write_text("One feature: add independent outputs.\n", encoding="utf-8")
        self.specification.write_text("AC1: outputs exist.\n", encoding="utf-8")
        self.path = self.root / "external workspace"
        self.approved = {"human": "test human", "evidence": "test session explicit approval", "date": "2026-11-03"}
        self.state = workflow.initialize(self.repo, self.path, "sample", self.ticket,
                                         self.specification, self.approved)

    def remove_test_directory(self):
        self.assertEqual(self.root.resolve().parent, self.temporary_parent)
        self.assertTrue(self.root.name.startswith("feature workflow tests "))

        def remove_readonly(function, path, error):
            if not isinstance(error[1], PermissionError):
                raise error[1]
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            function(path)

        shutil.rmtree(self.root, onerror=remove_readonly)

    def git(self, tree, *arguments):
        result = subprocess.run(["git", "-C", str(tree), *arguments], capture_output=True,
                                text=True, encoding="utf-8")
        if result.returncode:
            self.fail(result.stderr or result.stdout)
        return result.stdout.strip()

    def invoke(self, method, role="orchestrator", **arguments):
        with workflow.Workspace(self.path, "coordinator-session", role).transaction() as workspace:
            return getattr(workspace, method)(**arguments)

    def read(self):
        return json.loads((self.path / "state.json").read_text(encoding="utf-8"))

    def add(self, task="first", dependencies=None):
        self.invoke("add_task", role="planner", task_id=task, depends_on=dependencies or [],
                    scope=[task + ".txt"], acceptance_ids=["AC1"],
                    tests=[[sys.executable, "-c", "from pathlib import Path; assert Path('" + task + ".txt').exists()"]])

    def implement(self, task="first"):
        self.invoke("start_task", task_id=task, owner="author-" + task)
        tree = Path(self.read()["tasks"][task]["worktree"])
        (tree / (task + ".txt")).write_text(task + "\n", encoding="utf-8")
        self.git(tree, "add", task + ".txt")
        self.git(tree, "commit", "-m", "Implement " + task)
        self.invoke("submit", task_id=task)
        return tree

    def review(self, task="first", **changes):
        state = self.read()
        report = {"agent": "reviewer-" + task, "head": state["tasks"][task]["head"],
                  "spec_revision": state["spec_revision"], "tests": ["Scoped tests pass"],
                  "findings": [], "verdict": "pass"}
        report.update(changes)
        return self.invoke("review", task_id=task, report=report)

    def finish(self, task="first"):
        self.add(task)
        self.implement(task)
        self.review(task)
        return self.invoke("integrate", task_id=task)

    def gate(self, kind, **changes):
        state = self.read()
        report = {"agent": "independent-" + kind, "head": self.git(state["feature_worktree"], "rev-parse", "HEAD"),
                  "spec_revision": state["spec_revision"], "passed": True,
                  "evidence": ["Acceptance checks inspected and executed"]}
        report.update(changes)
        return self.invoke("gate", kind=kind, report=report)

    def test_initialization_preserves_dirty_staged_untracked_checkout(self):
        (self.repo / "tracked.txt").write_text("staged\n", encoding="utf-8")
        self.git(self.repo, "add", "tracked.txt")
        (self.repo / "tracked.txt").write_text("staged plus unstaged\n", encoding="utf-8")
        (self.repo / "private untracked.txt").write_text("private\n", encoding="utf-8")
        before = (self.git(self.repo, "rev-parse", "HEAD"), self.git(self.repo, "status", "--porcelain"),
                  self.git(self.repo, "diff", "--cached"), self.git(self.repo, "diff"))
        other = self.root / "another workspace"
        state = workflow.initialize(self.repo, other, "other", self.ticket, self.specification, self.approved)
        after = (self.git(self.repo, "rev-parse", "HEAD"), self.git(self.repo, "status", "--porcelain"),
                 self.git(self.repo, "diff", "--cached"), self.git(self.repo, "diff"))
        self.assertEqual(before, after)
        self.assertEqual(state["original"]["status"], before[1])
        self.assertEqual((other / "feature/tracked.txt").read_text(), "baseline\n")

    def test_initialization_rejects_existing_nested_unapproved_and_missing_instructions(self):
        for destination in (self.path, self.repo / "ignored workspace"):
            with self.assertRaises(ValueError):
                workflow.initialize(self.repo, destination, "other", self.ticket, self.specification, self.approved)
        with self.assertRaises(ValueError):
            workflow.initialize(self.repo, self.root / "unapproved", "other", self.ticket, self.specification, {})
        self.git(self.repo, "rm", "GLOSSARY.md")
        self.git(self.repo, "commit", "-m", "Remove initialization")
        with self.assertRaises(ValueError):
            workflow.initialize(self.repo, self.root / "uninitialized", "other", self.ticket, self.specification, self.approved)
        self.assertFalse((self.root / "uninitialized").exists())

    def test_authority_dependencies_and_no_completion_without_review(self):
        self.add()
        self.add("second", ["first"])
        with self.assertRaisesRegex(ValueError, "Dependencies"):
            self.invoke("start_task", task_id="second", owner="author-second")
        with self.assertRaises(ValueError):
            self.invoke("add_task", task_id="cycle", depends_on=["cycle"], scope=["x"], acceptance_ids=["AC1"], tests=[["true"]])
        with self.assertRaisesRegex(ValueError, "requires role"):
            self.invoke("start_task", role="implementer", task_id="first", owner="author-first")
        self.implement()
        with self.assertRaisesRegex(ValueError, "review"):
            self.invoke("integrate", task_id="first")
        self.assertEqual(self.read()["tasks"]["first"]["status"], "review")

    def test_parallel_tasks_review_and_serial_squash_integration(self):
        self.add("first")
        self.add("second")
        first = self.implement("first")
        second = self.implement("second")
        self.assertNotEqual(first, second)
        self.assertEqual(self.read()["tasks"]["first"]["base_commit"], self.read()["tasks"]["second"]["base_commit"])
        self.review("first")
        self.review("second")
        a = self.invoke("integrate", task_id="first")
        b = self.invoke("integrate", task_id="second")
        state = self.read()
        tree = state["feature_worktree"]
        self.assertEqual(self.git(tree, "rev-parse", b + "^"), a)
        self.assertEqual(self.git(tree, "rev-list", "--count", state["base_commit"] + "..HEAD"), "2")
        self.assertEqual(self.git(tree, "status", "--porcelain"), "")
        self.assertTrue(all(t["status"] == "complete" for t in state["tasks"].values()))
        self.assertTrue((Path(tree) / "first.txt").is_file())
        self.assertTrue((Path(tree) / "second.txt").is_file())
        with self.assertRaises(ValueError):
            self.invoke("integrate", task_id="first")

    def test_review_requires_independence_exact_head_revision_and_unchanged_tree(self):
        self.add()
        tree = self.implement()
        for change in ({"agent": "author-first"}, {"head": "0" * 40}, {"spec_revision": 99}):
            with self.assertRaises(ValueError):
                self.review(**change)
        self.review()
        (tree / "first.txt").write_text("edited after review\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after review"):
            self.invoke("integrate", task_id="first")

    def test_review_rejection_returns_task_for_repair(self):
        self.add()
        self.implement()
        self.review(verdict="fail", findings=[{"severity": "blocking", "location": "first.txt", "reason": "missing behavior"}])
        self.assertEqual(self.read()["tasks"]["first"]["status"], "implementing")
        with self.assertRaises(ValueError):
            self.invoke("integrate", task_id="first")

    def test_return_stale_review_for_repair_resubmit_and_integrate(self):
        self.add()
        tree = self.implement()
        self.review()
        (tree / "first.txt").write_text("repaired implementation\n", encoding="utf-8")
        self.git(tree, "add", "first.txt")
        self.git(tree, "commit", "-m", "Repair after reviewed submission")
        with self.assertRaises(ValueError):
            self.invoke("integrate", task_id="first")
        self.invoke("return_task", task_id="first", reason="Task changed; fresh independent review required")
        self.assertEqual(self.read()["tasks"]["first"]["status"], "implementing")
        self.invoke("submit", task_id="first")
        self.review()
        self.invoke("integrate", task_id="first")
        self.assertEqual(self.read()["tasks"]["first"]["status"], "complete")
        with self.assertRaises(ValueError):
            self.invoke("return_task", task_id="first", reason="Cannot rewrite completed history")

    def test_latest_requirements_invalidate_review_and_preserve_ticket(self):
        self.add()
        self.implement()
        self.review()
        ticket = (self.path / "ticket.md").read_bytes()
        self.specification.write_text("AC1: revised outputs.\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.invoke("revise", spec=str(self.specification), approved={}, affected_tasks=["first"])
        self.invoke("revise", spec=str(self.specification), approved=self.approved, affected_tasks=["first"])
        state = self.read()
        self.assertEqual(state["spec_revision"], 2)
        self.assertEqual(state["tasks"]["first"]["status"], "implementing")
        self.assertIsNone(state["tasks"]["first"]["review"])
        self.assertEqual((self.path / "ticket.md").read_bytes(), ticket)
        self.assertEqual((self.path / "specs/0001.md").read_text(), "AC1: outputs exist.\n")
        with self.assertRaises(ValueError):
            self.invoke("integrate", task_id="first")

    def test_ticket_tampering_incompatible_schema_and_live_lock_are_rejected(self):
        original = (self.path / "ticket.md").read_bytes()
        (self.path / "ticket.md").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "ticket changed"):
            self.invoke("pr_ready")
        (self.path / "ticket.md").write_bytes(original)
        state = self.read()
        state["schema_version"] = 99
        workflow.atomic_json(self.path / "state.json", state)
        with self.assertRaisesRegex(ValueError, "Incompatible"):
            self.invoke("pr_ready")
        (self.path / ".workflow.lock").write_text("another owner", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.invoke("pr_ready")
        self.assertEqual((self.path / ".workflow.lock").read_text(), "another owner")

    def test_mandatory_independent_current_gates_and_draft_readiness(self):
        self.finish()
        with self.assertRaisesRegex(ValueError, "validation"):
            self.invoke("pr_ready")
        with self.assertRaisesRegex(ValueError, "Independent"):
            self.gate("validation", agent="author-first")
        self.gate("validation")
        with self.assertRaisesRegex(ValueError, "quality"):
            self.invoke("pr_ready")
        self.gate("quality")
        self.assertTrue(self.invoke("pr_ready")["draft_only"])
        state = self.read()
        tree = Path(state["feature_worktree"])
        (tree / "extra.txt").write_text("extra\n", encoding="utf-8")
        self.git(tree, "add", "extra.txt")
        self.git(tree, "commit", "-m", "Further feature edit")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.invoke("pr_ready")

    def test_unaccounted_clean_feature_commit_blocks_dispatch_and_certification(self):
        self.finish()
        self.add("second")
        state = self.read()
        tree = Path(state["feature_worktree"])
        (tree / "unexpected.txt").write_text("unaccounted feature edit\n", encoding="utf-8")
        self.git(tree, "add", "unexpected.txt")
        self.git(tree, "commit", "-m", "Unexpected clean feature commit")
        self.assertEqual(self.git(tree, "status", "--porcelain"), "")
        with self.assertRaises(ValueError):
            self.invoke("start_task", task_id="second", owner="author-second")
        # Complete-task precondition can otherwise mask the HEAD guard; remove
        # the still-pending task record only in this deliberately corrupted fixture.
        state = self.read()
        del state["tasks"]["second"]
        workflow.atomic_json(self.path / "state.json", state)
        with self.assertRaises(ValueError):
            self.gate("validation")

    def test_failed_integration_checks_leave_recovery_checkpoint(self):
        self.add()
        self.implement()
        self.review()
        state = self.read()
        state["tasks"]["first"]["tests"] = [[sys.executable, "-c", "raise SystemExit(1)"]]
        workflow.atomic_json(self.path / "state.json", state)
        with self.assertRaisesRegex(ValueError, "checks failed"):
            self.invoke("integrate", task_id="first")
        state = self.read()
        self.assertEqual(state["tasks"]["first"]["status"], "reviewed")
        self.assertIsNotNone(state["integration"])
        with self.assertRaisesRegex(ValueError, "Unresolved integration"):
            self.invoke("integrate", task_id="first")
        with self.assertRaisesRegex(ValueError, "clean"):
            self.invoke("recover")

    def test_checks_that_modify_files_cannot_complete_integration(self):
        self.add()
        self.implement()
        self.review()
        state = self.read()
        state["tasks"]["first"]["tests"] = [[sys.executable, "-c",
            "from pathlib import Path; Path('first.txt').write_text('test changed implementation')"]]
        workflow.atomic_json(self.path / "state.json", state)
        with self.assertRaisesRegex(ValueError, "changed files"):
            self.invoke("integrate", task_id="first")
        self.assertEqual(self.read()["tasks"]["first"]["status"], "reviewed")
        self.assertEqual(self.git(state["feature_worktree"], "rev-parse", "HEAD"), state["base_commit"])

    def test_unaffected_review_is_requeued_on_spec_revision(self):
        self.add("first")
        self.add("second")
        self.implement("first")
        self.implement("second")
        self.review("first")
        self.review("second")
        self.specification.write_text("AC1: expanded first behavior.\n", encoding="utf-8")
        self.invoke("revise", spec=str(self.specification), approved=self.approved, affected_tasks=["first"])
        tasks = self.read()["tasks"]
        self.assertEqual(tasks["first"]["status"], "implementing")
        self.assertEqual(tasks["second"]["status"], "review")
        self.assertIsNone(tasks["second"]["review"])
        self.review("second")
        self.assertEqual(self.read()["tasks"]["second"]["status"], "reviewed")

    def test_committed_but_unsaved_integration_recovers_without_duplicate_commit(self):
        self.add()
        self.implement()
        self.review()
        original_atomic = workflow.atomic_json

        def interrupt_after_commit(path, value):
            if Path(path).name.startswith("result-"):
                raise OSError("simulated interruption after commit")
            return original_atomic(path, value)

        with patch.object(workflow, "atomic_json", side_effect=interrupt_after_commit):
            with self.assertRaisesRegex(OSError, "simulated interruption"):
                self.invoke("integrate", task_id="first")
        state = self.read()
        tree = state["feature_worktree"]
        head = self.git(tree, "rev-parse", "HEAD")
        self.assertEqual(state["tasks"]["first"]["status"], "reviewed")
        self.assertIsNotNone(state["integration"])
        result = self.invoke("recover")
        self.assertEqual(result, {"recovered": "committed", "head": head})
        self.assertEqual(self.git(tree, "rev-list", "--count", state["base_commit"] + "..HEAD"), "1")
        self.assertEqual(self.read()["tasks"]["first"]["status"], "complete")

    def cleanup_approval(self, ids):
        plan = self.invoke("cleanup_plan", resource_ids=ids)
        return dict(self.approved, feature_id="sample", inventory_sha256=plan["inventory_sha256"])

    def test_incremental_squash_cleanup_is_recoverable_and_repeatable(self):
        self.finish()
        state = self.read()
        head = state["tasks"]["first"]["head"]
        authorized = self.cleanup_approval(["task-first"])
        with self.assertRaises(ValueError):
            self.invoke("cleanup_apply", authorized=dict(authorized, inventory_sha256="wrong"))
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertEqual(result["removed"], ["task-first"])
        self.assertEqual(result["lifecycle"], "active")
        self.assertTrue((self.path / "feature").exists())
        self.assertFalse((self.path / "tasks/first").exists())
        self.assertEqual(self.git(self.repo, "rev-parse", "refs/feature-workflow/sample/task-first"), head)
        self.assertEqual(self.invoke("cleanup_apply", authorized=authorized)["blocked"], [])
        (self.path / "tasks/first").mkdir()
        (self.path / "tasks/first/new-user-file").write_text("preserve new work")
        self.assertTrue(self.invoke("cleanup_status")["blocked"])
        self.assertTrue((self.path / "tasks/first/new-user-file").exists())

    def test_cleanup_rechecks_dirty_ignored_branch_and_inventory(self):
        self.finish()
        authorized = self.cleanup_approval(["task-first"])
        tree = self.path / "tasks/first"
        private = tree / "private.txt"
        private.write_text("preserve")
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertTrue(result["blocked"])
        self.assertTrue(private.exists())
        private.unlink()
        self.git(tree, "checkout", "-b", "unrelated-branch")
        self.assertTrue(self.invoke("cleanup_apply", authorized=authorized)["blocked"])
        self.git(tree, "checkout", "codex/sample-task-first")
        self.assertFalse(self.invoke("cleanup_apply", authorized=authorized)["blocked"])

    def test_interrupted_cleanup_resumes_after_worktree_removal(self):
        self.finish()
        authorized = self.cleanup_approval(["task-first"])
        original_git = workflow.git
        def interrupted(repo, *args):
            if args[:2] == ("update-ref", "-d"):
                raise OSError("interrupted branch removal")
            return original_git(repo, *args)
        with patch.object(workflow, "git", side_effect=interrupted):
            result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertTrue(result["blocked"])
        self.assertFalse((self.path / "tasks/first").exists())
        state = self.read()
        branch = "refs/heads/" + state["tasks"]["first"]["branch"]
        self.git(self.repo, "update-ref", branch, state["integrated_head"])
        self.assertTrue(self.invoke("cleanup_apply", authorized=authorized)["blocked"])
        self.assertEqual(self.git(self.repo, "rev-parse", branch), state["integrated_head"])
        self.git(self.repo, "update-ref", branch, state["tasks"]["first"]["head"])
        self.assertEqual(self.invoke("cleanup_apply", authorized=authorized)["blocked"], [])

    def test_feature_cleanup_requires_merge_and_closed_is_separate(self):
        self.finish()
        with self.assertRaises(ValueError):
            self.cleanup_approval(["feature"])
        self.gate("validation")
        self.gate("quality")
        state = self.read()
        arguments = dict(url="https://example.invalid/pr/1", head=state["integrated_head"],
                         base="main", evidence="inspected provider PR identity and head")
        self.invoke("record_pr", **arguments)
        self.assertEqual(self.read()["lifecycle"], "published")
        with self.assertRaises(ValueError):
            self.cleanup_approval(["feature"])
        # Simulate a human/provider squash merge into the original base.
        self.git(self.repo, "merge", "--squash", arguments["head"])
        self.git(self.repo, "commit", "-m", "Provider squash merge")
        merge = self.git(self.repo, "rev-parse", "HEAD")
        self.invoke("record_pr", **dict(arguments, evidence="provider confirms merged", merge_commit=merge))
        self.assertEqual(self.read()["lifecycle"], "merged")
        authorized = self.cleanup_approval(["task-first", "feature"])
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertEqual(result["lifecycle"], "closed")
        self.assertEqual(result["blocked"], [])
        self.assertTrue((self.repo / "tracked.txt").exists())
        self.assertTrue((self.path / "state.json").exists())

    def test_unknown_directory_files_and_shared_docker_are_protected(self):
        directory = self.path / "temp with spaces"
        directory.mkdir()
        self.invoke("register_resource", resource_id="temp", kind="directory", owner="worker",
                    purpose="temporary", path=str(directory))
        authorized = self.cleanup_approval(["temp"])
        (directory / "unknown").write_text("retain")
        self.assertTrue(self.invoke("cleanup_apply", authorized=authorized)["blocked"])
        (directory / "unknown").unlink()
        self.assertFalse(self.invoke("cleanup_apply", authorized=authorized)["blocked"])
        self.invoke("register_resource", resource_id="network", kind="network", owner="worker",
                    purpose="tests", docker_id="a" * 64)
        shared = [{"Id": "a" * 64, "Labels": {"feature-workflow.feature": "sample",
                   "feature-workflow.owner": "worker"}, "Containers": {"other": {}}}]
        with patch.object(workflow.Workspace, "docker", return_value=json.dumps(shared)) as docker:
            with self.assertRaisesRegex(ValueError, "shared"):
                self.invoke("cleanup_plan", resource_ids=["network"])
            self.assertTrue(all(call.args[1] == "inspect" for call in docker.call_args_list))

    def test_ignored_files_and_missing_integration_proof_block_cleanup(self):
        self.finish()
        tree = self.path / "tasks/first"
        info = Path(self.git(tree, "rev-parse", "--git-common-dir")) / "info/exclude"
        info.write_text("private-output\n")
        (tree / "private-output").write_text("preserve ignored output")
        with self.assertRaisesRegex(ValueError, "Dirty/ignored"):
            self.cleanup_approval(["task-first"])
        (tree / "private-output").unlink()
        state = self.read()
        state["tasks"]["first"]["integration_evidence"]["source_head"] = "0" * 40
        workflow.atomic_json(self.path / "state.json", state)
        with self.assertRaisesRegex(ValueError, "integration"):
            self.cleanup_approval(["task-first"])

    def test_docker_resume_proves_absence_and_rejects_ownership_or_running_app(self):
        docker_id = "a" * 64
        self.invoke("register_resource", resource_id="container", kind="container", owner="worker",
                    purpose="tests", docker_id=docker_id)
        data = [{"Id": docker_id, "Config": {"Labels": {"feature-workflow.feature": "sample",
                 "feature-workflow.owner": "worker"}}, "State": {"Running": True}}]
        with patch.object(workflow.Workspace, "docker", return_value=json.dumps(data)):
            with self.assertRaisesRegex(ValueError, "Running"):
                self.cleanup_approval(["container"])
        data[0]["State"]["Running"] = False
        data[0]["Config"]["Labels"]["feature-workflow.owner"] = "other"
        with patch.object(workflow.Workspace, "docker", return_value=json.dumps(data)):
            with self.assertRaisesRegex(ValueError, "ownership"):
                self.cleanup_approval(["container"])
        data[0]["Config"]["Labels"]["feature-workflow.owner"] = "worker"
        with patch.object(workflow.Workspace, "docker", return_value=json.dumps(data)):
            authorized = self.cleanup_approval(["container"])
        present = [True]
        def daemon(*args):
            if args[1] == "inspect":
                return json.dumps(data)
            if args[1] == "ls":
                return docker_id if present[0] else ""
            if args[1] == "rm":
                present[0] = False
                raise OSError("interrupted after daemon removed container")
            raise AssertionError(args)
        with patch.object(workflow.Workspace, "docker", side_effect=daemon):
            self.assertTrue(self.invoke("cleanup_apply", authorized=authorized)["blocked"])
            self.assertEqual(self.invoke("cleanup_apply", authorized=authorized)["removed"], ["container"])

    def test_cli_reports_success_and_rejected_operation(self):
        request = self.root / "request with spaces.json"
        request.write_text(json.dumps(dict(task_id="cli", depends_on=[], scope=["cli.txt"],
            acceptance_ids=["AC1"], tests=[[sys.executable, "-c", "pass"]])), encoding="utf-8")
        command = [sys.executable, str(HELPER), "add-task", "--request", str(request),
                   "--workspace", str(self.path), "--actor", "cli-session", "--role", "planner"]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already exists", second.stderr)


if __name__ == "__main__":
    unittest.main()
