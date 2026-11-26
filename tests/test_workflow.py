"""Integration tests use disposable local Git repositories; no network or live checkout edits."""
import hashlib
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
        self.path = self.root / "original repo-features" / "sample"
        self.approved = {"human": "test human", "evidence": "test session explicit approval", "date": "2026-11-03"}
        self.state = workflow.initialize(self.repo, "sample", self.ticket,
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
        self.git(tree, "commit", "-m", "Add independent output in " + task + ".txt")
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
        return self.invoke("integrate", task_id=task, message="Add independent output in " + task + ".txt")

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
        other = self.path.parent / "other"
        state = workflow.initialize(self.repo, "other", self.ticket, self.specification, self.approved,
                                    workspace=other)
        after = (self.git(self.repo, "rev-parse", "HEAD"), self.git(self.repo, "status", "--porcelain"),
                 self.git(self.repo, "diff", "--cached"), self.git(self.repo, "diff"))
        self.assertEqual(before, after)
        self.assertEqual(state["original"]["status"], before[1])
        self.assertEqual((other / "feature/tracked.txt").read_text(), "baseline\n")

    def test_cli_derives_workspace_from_primary_checkout_when_called_from_linked_checkout(self):
        checkout = self.state["feature_worktree"]
        self.git(checkout, "commit", "--allow-empty", "-m", "Linked checkout baseline")
        request = self.root / "init request.json"
        request.write_text(json.dumps(dict(repo=checkout, feature_id="linked",
                                           ticket=str(self.ticket), spec=str(self.specification),
                                           approved=self.approved)), encoding="utf-8")
        result = subprocess.run([sys.executable, str(HELPER), "init", "--request", str(request),
                                 "--actor", "cli-session", "--role", "planner"], capture_output=True,
                                text=True, encoding="utf-8", check=True)
        state = json.loads(result.stdout)
        expected = self.path.parent / "linked"
        self.assertEqual(Path(state["feature_worktree"]), expected / "feature")
        self.assertTrue((expected / "state.json").is_file())
        self.assertEqual(state["base_commit"], self.git(checkout, "rev-parse", "HEAD"))

    def test_initialization_with_separate_git_metadata_requires_primary_checkout_path(self):
        primary = self.root / "separate checkout"
        metadata = self.root / "separate metadata"
        primary.mkdir()
        self.git(primary, "init", "--separate-git-dir", str(metadata), "-b", "main")
        for name in ("AGENTS.md", "GLOSSARY.md"):
            shutil.copyfile(self.repo / name, primary / name)
        self.git(primary, "add", ".")
        self.git(primary, "-c", "user.name=Workflow Test", "-c", "user.email=workflow@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-m", "Separate metadata baseline")
        linked = self.root / "separate linked checkout"
        self.git(primary, "worktree", "add", "-b", "linked", str(linked))
        refs = self.git(primary, "show-ref")
        expected = self.root / "separate checkout-features" / "separate"
        fallback = self.root / "separate metadata-features"
        with self.assertRaisesRegex(ValueError, "Pass the primary checkout as repo"):
            workflow.initialize(linked, "separate", self.ticket, self.specification, self.approved)
        self.assertFalse(expected.exists())
        self.assertFalse(fallback.exists())
        self.assertEqual(self.git(primary, "show-ref"), refs)
        state = workflow.initialize(primary, "separate", self.ticket, self.specification, self.approved)
        self.assertEqual(Path(state["feature_worktree"]), expected / "feature")
        self.assertFalse(fallback.exists())

    def test_invalid_initialization_leaves_paths_and_refs_untouched(self):
        other = self.path.parent / "other"
        fallback = self.root / "arbitrary workspace"
        refs = self.git(self.repo, "show-ref")
        with self.assertRaisesRegex(ValueError, "Feature workspace already exists"):
            workflow.initialize(self.repo, "sample", self.ticket, self.specification, self.approved)
        for destination in (fallback, self.repo / "ignored workspace"):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(ValueError, "Feature workspace must be"):
                    workflow.initialize(self.repo, "other", self.ticket, self.specification,
                                        self.approved, workspace=destination)
                self.assertFalse(destination.exists())
        with self.assertRaisesRegex(ValueError, "identifier"):
            workflow.initialize(self.repo, "../other", self.ticket, self.specification, self.approved)
        with self.assertRaisesRegex(ValueError, "approval"):
            workflow.initialize(self.repo, "other", self.ticket, self.specification, {})
        self.assertEqual(self.git(self.repo, "show-ref"), refs)
        self.git(self.repo, "rm", "GLOSSARY.md")
        self.git(self.repo, "commit", "-m", "Remove initialization")
        refs = self.git(self.repo, "show-ref")
        with self.assertRaisesRegex(ValueError, "GLOSSARY.md"):
            workflow.initialize(self.repo, "other", self.ticket, self.specification, self.approved)
        self.assertFalse(other.exists())
        self.assertEqual(self.git(self.repo, "show-ref"), refs)

    def test_initialization_rejects_target_under_another_git_checkout(self):
        self.git(self.path.parent, "init", "-b", "main")
        with self.assertRaisesRegex(ValueError, "outside any Git checkout"):
            workflow.initialize(self.repo, "nested", self.ticket, self.specification, self.approved)
        self.assertFalse((self.path.parent / "nested").exists())

    def test_initialization_reports_denied_workspace_without_creating_refs(self):
        destination = self.path.parent / "denied"
        refs = self.git(self.repo, "show-ref")
        with patch.object(Path, "mkdir", side_effect=PermissionError("sandbox denied")) as mkdir:
            with self.assertRaisesRegex(ValueError, "Write access to required feature workspace denied") as error:
                workflow.initialize(self.repo, "denied", self.ticket, self.specification, self.approved)
        mkdir.assert_called_once_with(parents=True, exist_ok=False)
        self.assertIn(str(destination), str(error.exception))
        self.assertIn("sandbox denied", str(error.exception))
        self.assertEqual(self.git(self.repo, "show-ref"), refs)
        self.assertFalse(destination.exists())

    def test_task_and_review_worktrees_are_under_the_feature_workspace(self):
        self.add()
        task_tree = self.implement()
        self.assertEqual(task_tree, self.path / "tasks" / "first")
        review_tree = self.path / "reviews" / "first-review"
        review_branch = "codex/sample-review-first"
        self.git(self.repo, "worktree", "add", "-b", review_branch, str(review_tree),
                 self.read()["tasks"]["first"]["head"])
        resource = dict(resource_id="first-review", kind="worktree", owner="reviewer-first",
                        purpose="review", branch=review_branch, task_id="first")
        with self.assertRaisesRegex(ValueError, "Review worktree must be under"):
            self.invoke("register_resource", path=str(self.root / "outside"), **resource)
        self.invoke("register_resource", path=str(review_tree), **resource)
        self.assertEqual(self.read()["resources"]["first-review"]["path"], str(review_tree))

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
            self.invoke("integrate", task_id="first", message="Add independent output in first.txt")
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
        a = self.invoke("integrate", task_id="first", message="Add independent output in first.txt")
        b = self.invoke("integrate", task_id="second", message="Add independent output in second.txt")
        state = self.read()
        tree = state["feature_worktree"]
        self.assertEqual(self.git(tree, "rev-parse", b + "^"), a)
        self.assertEqual(self.git(tree, "rev-list", "--count", state["base_commit"] + "..HEAD"), "2")
        self.assertEqual(self.git(tree, "status", "--porcelain"), "")
        self.assertTrue(all(t["status"] == "complete" for t in state["tasks"].values()))
        self.assertTrue((Path(tree) / "first.txt").is_file())
        self.assertTrue((Path(tree) / "second.txt").is_file())
        with self.assertRaises(ValueError):
            self.invoke("integrate", task_id="first", message="Add independent output in first.txt")

    def test_squash_message_describes_entire_task_and_preserves_evidence(self):
        self.add()
        worker = self.implement()
        (worker / "first.txt").write_text("output with retry behavior\n", encoding="utf-8")
        self.git(worker, "add", "first.txt")
        self.git(worker, "commit", "-m", "Cover retry behavior after authentication fails")
        self.invoke("return_task", task_id="first", reason="Include the retry repair in independent review")
        self.invoke("submit", task_id="first")
        self.review()
        reviewed = self.read()["tasks"]["first"]["head"]
        description = ("Fix login button remaining disabled after a failed sign-in\n\n"
                       "Re-enable retry after authentication fails so users can correct their credentials.")
        head = self.invoke("integrate", task_id="first", message=description)
        state = self.read()
        expected = (description + "\n\nFeature: sample\nTask: first\nSource-Head: " + reviewed +
                    "\nSpec-Revision: 1")
        self.assertEqual(self.git(state["feature_worktree"], "log", "-1", "--format=%B"), expected)
        self.assertEqual(self.git(worker, "rev-list", "--count", state["base_commit"] + "..HEAD"), "2")
        self.assertEqual(self.git(state["feature_worktree"], "rev-list", "--count", state["base_commit"] + "..HEAD"), "1")
        self.assertEqual(state["tasks"]["first"]["integration_commit"], head)
        self.assertEqual(state["tasks"]["first"]["integration_evidence"]["source_head"], reviewed)

    def test_invalid_integration_messages_fail_before_git_or_checkpoint_mutation(self):
        self.add()
        self.implement()
        self.review()
        before = (self.path / "state.json").read_bytes()
        tree = self.read()["feature_worktree"]
        checkpoints = sorted(p.name for p in (self.path / "checkpoints").iterdir())
        invalid = [None, False, 42, [], {}, "", " \r\n\t", "Implement first", "Integrate 01",
                   "Fix task 01", "Implement <task-id>", "Fix login\nBody without separator",
                   "Fix login\0button"]
        for key in ("Feature", "Task", "Source-Head", "Spec-Revision"):
            invalid.extend(["Fix login retry\n\n" + key + ": forged",
                            "Fix login retry\n\n  " + key.lower() + " = forged"])
        for message in invalid:
            with self.subTest(message=message):
                with self.assertRaises(ValueError):
                    self.invoke("integrate", task_id="first", message=message)
                self.assertEqual((self.path / "state.json").read_bytes(), before)
                self.assertEqual(self.git(tree, "rev-parse", "HEAD"), self.read()["integrated_head"])
                self.assertEqual(self.git(tree, "status", "--porcelain"), "")
                self.assertEqual(sorted(p.name for p in (self.path / "checkpoints").iterdir()), checkpoints)
        with self.assertRaises(TypeError):
            self.invoke("integrate", task_id="first")
        self.assertEqual((self.path / "state.json").read_bytes(), before)
        request = self.root / "integration request with spaces.json"
        request.write_text(json.dumps({"task_id": "first"}), encoding="utf-8")
        result = subprocess.run([sys.executable, str(HELPER), "integrate", "--request", str(request),
                                 "--workspace", str(self.path), "--actor", "cli-session", "--role", "orchestrator"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("message", result.stderr)
        self.assertEqual((self.path / "state.json").read_bytes(), before)

    def test_review_requires_independence_exact_head_revision_and_unchanged_tree(self):
        self.add()
        tree = self.implement()
        for change in ({"agent": "author-first"}, {"head": "0" * 40}, {"spec_revision": 99}):
            with self.assertRaises(ValueError):
                self.review(**change)
        self.review()
        (tree / "first.txt").write_text("edited after review\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after review"):
            self.invoke("integrate", task_id="first", message="Add independent output in first.txt")

    def test_review_rejection_returns_task_for_repair(self):
        self.add()
        self.implement()
        self.review(verdict="fail", findings=[{"severity": "blocking", "location": "first.txt", "reason": "missing behavior"}])
        self.assertEqual(self.read()["tasks"]["first"]["status"], "implementing")
        with self.assertRaises(ValueError):
            self.invoke("integrate", task_id="first", message="Add independent output in first.txt")

    def test_return_stale_review_for_repair_resubmit_and_integrate(self):
        self.add()
        tree = self.implement()
        self.review()
        (tree / "first.txt").write_text("repaired implementation\n", encoding="utf-8")
        self.git(tree, "add", "first.txt")
        self.git(tree, "commit", "-m", "Repair after reviewed submission")
        with self.assertRaises(ValueError):
            self.invoke("integrate", task_id="first", message="Add independent output in first.txt")
        self.invoke("return_task", task_id="first", reason="Task changed; fresh independent review required")
        self.assertEqual(self.read()["tasks"]["first"]["status"], "implementing")
        self.invoke("submit", task_id="first")
        self.review()
        self.invoke("integrate", task_id="first", message="Add independent output in first.txt")
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
            self.invoke("integrate", task_id="first", message="Add independent output in first.txt")

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
            self.invoke("integrate", task_id="first", message="Add independent output in first.txt")
        state = self.read()
        self.assertEqual(state["tasks"]["first"]["status"], "reviewed")
        self.assertIsNotNone(state["integration"])
        with self.assertRaisesRegex(ValueError, "Unresolved integration"):
            self.invoke("integrate", task_id="first", message="Add independent output in first.txt")
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
            self.invoke("integrate", task_id="first", message="Add independent output in first.txt")
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
        self.assert_interrupted_integration_recovers(legacy=False)

    def test_legacy_generic_integration_still_recovers(self):
        self.assert_interrupted_integration_recovers(legacy=True)

    def assert_interrupted_integration_recovers(self, legacy):
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
                self.invoke("integrate", task_id="first", message="Add independent output in first.txt")
        state = self.read()
        tree = state["feature_worktree"]
        head = self.git(tree, "rev-parse", "HEAD")
        self.assertEqual(state["tasks"]["first"]["status"], "reviewed")
        self.assertIsNotNone(state["integration"])
        # Legacy schema-2 checkpoints contain no requested message; their generic
        # subjects remain recoverable through the original parent/tree/trailer evidence.
        if legacy:
            self.git(tree, "commit", "--amend", "-m", "Integrate first\n\nFeature: sample\nTask: first\nSource-Head: " +
                     state["tasks"]["first"]["head"] + "\nSpec-Revision: 1")
            head = self.git(tree, "rev-parse", "HEAD")
        result = self.invoke("recover")
        self.assertEqual(result, {"recovered": "committed", "head": head})
        self.assertEqual(self.git(tree, "rev-list", "--count", state["base_commit"] + "..HEAD"), "1")
        self.assertEqual(self.read()["tasks"]["first"]["status"], "complete")

    def cleanup_approval(self, ids):
        plan = self.invoke("cleanup_plan", resource_ids=ids)
        return dict(self.approved, feature_id="sample", inventory_sha256=plan["inventory_sha256"])

    def attempt(self, resource_id, purpose, head, owner, task_id=None):
        folder = "reviews" if purpose == "review" else "gates"
        tree = self.path / folder / resource_id
        branch = "codex/sample-" + resource_id
        self.git(self.repo, "worktree", "add", "-b", branch, str(tree), head)
        self.invoke("register_resource", resource_id=resource_id, kind="worktree",
                    owner=owner, purpose=purpose, path=str(tree), branch=branch,
                    task_id=task_id, track_attempt=purpose == "review")
        return tree

    def attempt_report(self, resource_id, **changes):
        attempt = self.read()["resources"][resource_id]["attempt"]
        report = dict(resource_id=resource_id, agent=attempt["owner"], head=attempt["head"],
                      spec_revision=attempt["spec_revision"])
        if attempt["purpose"] == "review":
            report.update(task_id=attempt["task_id"], verdict="fail", tests=["Checks completed"], findings=[])
        else:
            report.update(kind=attempt["purpose"], passed=False, evidence=["Checks completed"])
        report.update(changes)
        return report

    def test_cleanup_accepts_failed_and_superseded_gate_worktrees_without_passing_gates(self):
        head = self.finish()
        for kind in ("validation", "quality"):
            resource = kind + "-one"
            self.attempt(resource, kind, head, "independent-" + kind)
            report = self.attempt_report(resource, passed=kind == "validation")
            self.invoke("finish_worktree_attempt", resource_id=resource, report=report)
            self.gate(kind, passed=False)
        self.specification.write_text("AC1: revised outputs exist.\n", encoding="utf-8")
        self.invoke("revise", spec=str(self.specification), approved=self.approved, affected_tasks=[])
        with self.assertRaisesRegex(ValueError, "Missing/stale validation gate"):
            self.invoke("pr_ready")
        authorized = self.cleanup_approval(["validation-one", "quality-one"])
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertEqual(set(result["removed"]), {"validation-one", "quality-one"})
        self.assertEqual(result["blocked"], [])
        self.assertEqual(self.read()["gates"], {})
        for resource in ("validation-one", "quality-one"):
            record = self.read()["resources"][resource]["attempt"]["report"]
            self.assertTrue((self.path / "reports" / record["file"]).is_file())
            self.assertEqual(self.git(self.repo, "rev-parse", "refs/feature-workflow/sample/" + resource), head)

    def test_tracked_review_blocks_new_and_persisted_legacy_path_aliases(self):
        self.add()
        self.implement()
        source = self.read()["tasks"]["first"]["head"]
        resource_id = "tracked-review"
        tree = self.attempt(resource_id, "review", source, "tracked-reviewer", task_id="first")
        alias = dict(resource_id="legacy-alias", kind="worktree", owner="reviewer-first",
                     purpose="review", path=str(tree), branch="codex/sample-tracked-review", task_id="first")
        with self.assertRaisesRegex(ValueError, "overlaps a registered resource"):
            self.invoke("register_resource", **alias)

        self.review()
        self.invoke("integrate", task_id="first", message="Add the reviewed first output")
        state = self.read()
        tracked = state["resources"].pop(resource_id)
        workflow.atomic_json(self.path / "state.json", state)
        self.invoke("register_resource", **alias)
        authorized = self.cleanup_approval(["legacy-alias"])
        # A previously persisted conflicting record cannot bypass attempt verification.
        state = self.read()
        state["resources"][resource_id] = tracked
        workflow.atomic_json(self.path / "state.json", state)
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("overlaps a registered resource", result["blocked"][0]["error"])
        self.assertTrue(tree.is_dir())
        self.assertEqual(self.git(self.repo, "rev-parse", "refs/heads/" + alias["branch"]), source)

    def test_gate_worktree_rejects_foreign_repository_at_same_branch_and_head(self):
        head = self.finish()
        resource = "quality-foreign"
        branch = "codex/sample-quality-foreign"
        tree = self.attempt(resource, "quality", head, "independent-quality")
        self.invoke("finish_worktree_attempt", resource_id=resource, report=self.attempt_report(resource))
        tree.rename(tree.with_name("displaced-checkout"))
        tree.mkdir()
        self.git(tree, "init", "-b", branch)
        alternates = tree / ".git/objects/info/alternates"
        alternates.write_text((self.repo / ".git/objects").as_posix() + "\n", encoding="utf-8", newline="\n")
        self.git(tree, "update-ref", "refs/heads/" + branch, head)
        self.git(tree, "read-tree", "--reset", "-u", "HEAD")
        self.assertEqual(self.git(tree, "rev-parse", "HEAD"), head)
        with self.assertRaisesRegex(ValueError, "repository mismatch"):
            self.cleanup_approval([resource])

    def test_gate_worktree_cleanup_requires_registered_matching_finished_attempt(self):
        head = self.finish()
        resource = "quality-one"
        tree = self.attempt(resource, "quality", head, "independent-quality")
        self.gate("quality")
        with self.assertRaisesRegex(ValueError, "completed worktree attempt"):
            self.cleanup_approval([resource])
        report = self.attempt_report(resource)
        for field, value in (("agent", "unrelated"), ("head", "0" * 40), ("spec_revision", 2),
                             ("kind", "validation"), ("resource_id", "another-attempt")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "attempt"):
                self.invoke("finish_worktree_attempt", resource_id=resource, report=dict(report, **{field: value}))
        self.invoke("finish_worktree_attempt", resource_id=resource, report=report)
        authorized = self.cleanup_approval([resource])
        path = self.path / "reports" / self.read()["resources"][resource]["attempt"]["report"]["file"]
        saved = path.read_bytes()
        path.unlink()
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("Missing preserved", result["blocked"][0]["error"])
        path.write_bytes(saved + b" ")
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("report changed", result["blocked"][0]["error"])
        path.write_bytes(saved)
        self.git(tree, "commit", "--allow-empty", "-m", "Advance the gate checkout after approval")
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("attempt identity changed", result["blocked"][0]["error"])
        self.git(tree, "update-ref", "refs/heads/codex/sample-quality-one", head)
        self.git(tree, "checkout", "-b", "unrelated-worktree-branch")
        self.assertTrue(self.invoke("cleanup_apply", authorized=authorized)["blocked"])
        self.git(tree, "checkout", "codex/sample-quality-one")
        self.assertFalse(self.invoke("cleanup_apply", authorized=authorized)["blocked"])

    def test_superseded_review_cleanup_preserves_the_old_unintegrated_tip(self):
        self.add()
        task_tree = self.implement()
        source = self.read()["tasks"]["first"]["head"]
        old = "first-review-old"
        old_tree = self.attempt(old, "review", source, "reviewer-old", task_id="first")
        report = self.attempt_report(old)
        with self.assertRaisesRegex(ValueError, "review attempt"):
            self.invoke("finish_worktree_attempt", resource_id=old, report=dict(report, task_id="another"))
        self.invoke("finish_worktree_attempt", resource_id=old, report=report)
        self.invoke("review", task_id="first", report=report)
        with self.assertRaisesRegex(ValueError, "Unintegrated"):
            self.cleanup_approval([old])
        (task_tree / "first.txt").write_text("review repair\n", encoding="utf-8")
        self.git(task_tree, "add", "first.txt")
        self.git(task_tree, "commit", "-m", "Revise first output after review")
        self.invoke("submit", task_id="first")
        final = self.read()["tasks"]["first"]["head"]
        final_id = "first-review-final"
        self.attempt(final_id, "review", final, "reviewer-final", task_id="first")
        accepted = self.attempt_report(final_id, verdict="pass")
        self.invoke("finish_worktree_attempt", resource_id=final_id, report=accepted)
        self.invoke("review", task_id="first", report=accepted)
        self.invoke("integrate", task_id="first", message="Add the reviewed first output")

        authorized = self.cleanup_approval([old, final_id, "task-first"])
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertEqual(result["blocked"], [])
        self.assertFalse(old_tree.exists())
        self.assertEqual(self.git(self.repo, "rev-parse", "refs/feature-workflow/sample/" + old), source)
        self.assertEqual(self.git(self.repo, "rev-parse", "refs/feature-workflow/sample/" + final_id), final)

    def test_review_finished_after_integration_lacks_proof_of_supersession(self):
        self.add()
        self.implement()
        source = self.read()["tasks"]["first"]["head"]
        resource = "first-review-open"
        self.attempt(resource, "review", source, "reviewer-open", task_id="first")
        self.review()
        self.invoke("integrate", task_id="first", message="Add the reviewed first output")
        with self.assertRaisesRegex(ValueError, "completed worktree attempt"):
            self.cleanup_approval([resource])
        self.invoke("finish_worktree_attempt", resource_id=resource, report=self.attempt_report(resource))
        with self.assertRaisesRegex(ValueError, "No later review"):
            self.cleanup_approval([resource])

    def test_pending_legacy_review_inventory_resumes_with_a_distinct_resource_owner(self):
        self.finish()
        state = self.read()
        task = state["tasks"]["first"]
        task.pop("review_evidence")
        head = task["head"]
        resource_id = "legacy-final"
        tree = self.path / "reviews" / resource_id
        branch = "codex/sample-legacy-final"
        self.git(self.repo, "worktree", "add", "-b", branch, str(tree), head)

        # Reconstruct the persisted schema-2 inventory from before attempt tracking.
        resource = dict(kind="worktree", owner="review-worktree-coordinator", purpose="review",
                        path=str(tree), branch=branch, task_id="first", docker_id=None, status="present")
        self.assertNotEqual(resource["owner"], task["review"]["agent"])
        state["resources"][resource_id] = resource
        inventory = [dict(resource_id=resource_id, head=head, **resource)]
        token = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
        state["cleanup"] = dict(inventory=inventory, inventory_sha256=token,
                                items=[dict(resource_id=resource_id, status="pending")])
        authorized = dict(self.approved, feature_id="sample", inventory_sha256=token)
        state["cleanup_authorization"] = authorized
        workflow.atomic_json(self.path / "state.json", state)

        private = tree / "private.txt"
        private.write_text("retain until explicitly removed", encoding="utf-8")
        blocked = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("Dirty/ignored", blocked["blocked"][0]["error"])
        private.unlink()
        if os.name == "nt":
            stream = Path(str(tree / "first.txt") + ":unrecorded")
            stream.write_bytes(b"retain legacy checkout data")
            try:
                blocked = self.invoke("cleanup_apply", authorized=authorized)
                self.assertIn("Named Windows data stream retained", blocked["blocked"][0]["error"])
                self.assertEqual(stream.read_bytes(), b"retain legacy checkout data")
            finally:
                stream.unlink()
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertEqual(result["removed"], [resource_id])
        self.assertEqual(result["blocked"], [])
        self.assertEqual(self.read()["cleanup"]["inventory"], inventory)
        self.assertEqual(self.git(self.repo, "rev-parse", "refs/feature-workflow/sample/" + resource_id), head)

    def build_output(self, resource_id, directories, source):
        return self.invoke("record_build_output", resource_id=resource_id, directories=directories,
                           command=[sys.executable, "-c", "from pathlib import Path\n" + source])

    def test_build_output_inventory_records_exact_ignored_and_untracked_contents(self):
        head = self.finish()
        resource_id = "validation-build"
        tree = self.attempt(resource_id, "validation", head, "independent-validation")
        exclude = self.repo / ".git/info/exclude"
        exclude.write_text("ignored output/\n", encoding="utf-8")
        reference = self.build_output(resource_id, ["plain output", "ignored output"], """
Path("plain output").mkdir()
Path("plain output/file with spaces").write_bytes(b"plain")
Path("ignored output/nested/empty").mkdir(parents=True)
Path("ignored output/nested/result").write_bytes(b"ignored")
""")
        with self.assertRaisesRegex(ValueError, "completed worktree attempt"):
            self.cleanup_approval([resource_id])
        self.invoke("finish_worktree_attempt", resource_id=resource_id, report=self.attempt_report(resource_id))
        report_path = self.path / "reports" / reference["file"]
        self.assertEqual(workflow.digest(report_path), reference["sha256"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["worktree"]["head"], head)
        self.assertEqual(report["worktree"]["path"], str(tree))
        self.assertEqual(report["worktree"]["resource_id"], resource_id)
        self.assertEqual(report["before"], {})
        self.assertEqual(report["exit_code"], 0)

        authorized = self.cleanup_approval([resource_id])
        snapshot = self.read()["cleanup"]["inventory"][0]
        self.assertEqual(snapshot["build_output"]["reports"], [reference])
        inventory = snapshot["output_inventory"]
        self.assertEqual(inventory["directories"], ["ignored output", "plain output"])
        self.assertEqual(inventory["entries"], report["after"])
        self.assertEqual(inventory["generated"], [
            "ignored output", "ignored output/nested", "ignored output/nested/empty",
            "ignored output/nested/result", "plain output", "plain output/file with spaces",
        ])
        file_proof = inventory["entries"]["ignored output/nested/result"]
        self.assertEqual(file_proof["size"], len(b"ignored"))
        self.assertEqual(file_proof["sha256"], hashlib.sha256(b"ignored").hexdigest())
        self.assertEqual(inventory["entries"]["ignored output/nested/empty"]["kind"], "directory")

    def test_build_output_carries_only_verified_files_across_builds(self):
        self.finish()
        resource_id = "task-first"
        root = self.path / "tasks/first"
        self.build_output(resource_id, ["generated"], """
Path("generated").mkdir()
Path("generated/verified").write_bytes(b"first")
""")
        self.build_output(resource_id, ["generated"], """
Path("generated/verified").rename("generated/moved verified")
Path("generated/verified").write_bytes(b"rebuilt")
Path("generated/second").write_bytes(b"second")
""")
        with workflow.Workspace(self.path, "coordinator-session", "orchestrator").transaction() as workspace:
            resource = workspace.state["resources"][resource_id]
            output = workspace.inspect_resource(resource)["output_inventory"]
        self.assertEqual(output["generated"], [
            "generated", "generated/moved verified", "generated/second", "generated/verified",
        ])
        self.assertEqual(output["entries"]["generated/moved verified"]["sha256"], hashlib.sha256(b"first").hexdigest())
        self.assertEqual(output["entries"]["generated/verified"]["sha256"], hashlib.sha256(b"rebuilt").hexdigest())

        unknown = root / "generated/private"
        unknown.write_bytes(b"private before a later build")
        for _ in range(2):
            self.build_output(resource_id, ["generated"], """
Path("generated/private").write_bytes(b"overwritten but not attributable")
Path("generated/verified").write_bytes(b"rebuilt")
""")
            with self.assertRaisesRegex(ValueError, "Unknown files retained inside"):
                self.cleanup_approval([resource_id])
        self.assertTrue(unknown.exists())
        self.build_output(resource_id, ["generated"], """
Path("generated/private").rename("generated/renamed private")
""")
        with self.assertRaisesRegex(ValueError, "Unknown files retained inside"):
            self.cleanup_approval([resource_id])
        self.build_output(resource_id, ["generated"], """
Path("generated/renamed private").unlink()
Path("generated/renamed private").write_bytes(b"new inode, same unknown path")
""")
        with self.assertRaisesRegex(ValueError, "Unknown files retained inside"):
            self.cleanup_approval([resource_id])

    def test_build_output_blocks_unknown_changed_or_replaced_output(self):
        self.finish()
        resource_id = "task-first"
        tree = self.path / "tasks/first"
        result = tree / "generated/result"
        self.build_output(resource_id, ["generated"], """
Path("generated").mkdir()
Path("generated/result").write_bytes(b"original")
""")

        exclude = self.repo / ".git/info/exclude"
        exclude.write_text("outside ignored\n", encoding="utf-8")
        outside = tree / "outside ignored"
        outside.write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "Unverified untracked or ignored files"):
            self.cleanup_approval([resource_id])
        outside.unlink()

        nested = tree / "generated/manual addition"
        nested.mkdir()
        (nested / "private").write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "Build output contents changed"):
            self.cleanup_approval([resource_id])
        (nested / "private").unlink()
        nested.rmdir()

        for name in ("outside untracked", "outside ignored"):
            with self.subTest(outside=name):
                untouched = tree / name
                untouched.write_bytes(b"may not move unverified contents into the recorded root")
                with self.assertRaisesRegex(ValueError, "Unverified untracked or ignored"):
                    self.build_output(resource_id, ["generated"], f"""
Path({name!r}).rename("generated/moved outside file")
""")
                self.assertTrue(untouched.is_file())
                self.assertFalse((tree / "generated/moved outside file").exists())
                untouched.unlink()

        saved = self.root / "original output file"
        result.rename(saved)
        result.write_bytes(saved.read_bytes())
        with self.assertRaisesRegex(ValueError, "Build output contents changed"):
            self.cleanup_approval([resource_id])

    def test_build_output_rejects_failed_builds_tracked_edits_and_unsafe_paths(self):
        self.finish()
        resource_id = "task-first"
        tree = self.path / "tasks/first"
        build = dict(resource_id=resource_id, directories=["generated"],
                     command=[sys.executable, "-c", """
from pathlib import Path
Path("generated").mkdir()
Path("generated/leftover").write_bytes(b"unverified")
raise SystemExit(17)
"""])
        with self.assertRaisesRegex(ValueError, "Operation requires role"):
            self.invoke("record_build_output", role="planner", **build)
        with self.assertRaisesRegex(ValueError, "Build command failed with exit code 17"):
            self.invoke("record_build_output", **build)
        self.assertNotIn("build_output", self.read()["resources"][resource_id])
        self.assertFalse(list((self.path / "reports").glob("build-output-*")))
        with self.assertRaisesRegex(ValueError, "Dirty/ignored"):
            self.cleanup_approval([resource_id])

        for directories in (["../escape"], [str(tree / "generated")], [".git"],
                            ["generated", "generated/nested"], ["generated", "generated"]):
            with self.subTest(directories=directories), self.assertRaisesRegex(
                    ValueError, "Unsafe output directory|Output directories must be distinct"):
                self.build_output(resource_id, directories, "raise SystemExit('must not run')")
        with self.assertRaisesRegex(ValueError, "Output directory overlaps a tracked"):
            self.build_output(resource_id, ["tracked.txt"], "raise SystemExit('must not run')")

        (tree / "tracked.txt").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "Tracked or staged"):
            self.build_output(resource_id, ["generated"], "raise SystemExit('must not run')")
        self.git(tree, "add", "--", "tracked.txt")
        with self.assertRaisesRegex(ValueError, "Tracked or staged"):
            self.build_output(resource_id, ["generated"], "raise SystemExit('must not run')")
        self.git(tree, "restore", "--source=HEAD", "--staged", "--worktree", "--", "tracked.txt")

        self.git(tree, "update-index", "--assume-unchanged", "--", "tracked.txt")
        (tree / "tracked.txt").write_bytes(b"hidden tracked edit")
        with self.assertRaisesRegex(ValueError, "Index flags can conceal"):
            self.build_output(resource_id, ["generated"], "raise SystemExit('must not run')")

    def test_build_output_rejects_links_within_declared_directories(self):
        self.finish()
        resource_id = "task-first"
        tree = self.path / "tasks/first"
        preserve = self.root / "untouched outside"
        preserve.write_bytes(b"outside")
        with self.assertRaisesRegex(ValueError, "linked output file"):
            self.build_output(resource_id, ["generated"], f"""
import os
Path("generated").mkdir()
os.link({str(preserve)!r}, "generated/hard link")
""")
        self.assertEqual(preserve.read_bytes(), b"outside")
        self.assertNotIn("build_output", self.read()["resources"][resource_id])

        (tree / "generated/hard link").unlink()
        if os.name == "nt":
            subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", "linked-root", str(self.root)],
                           cwd=tree, capture_output=True, check=True)
            self.addCleanup(lambda: (tree / "linked-root").rmdir())
        else:
            (tree / "linked-root").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Unsafe cleanup path|Linked cleanup path"):
            self.build_output(resource_id, ["linked-root"], "raise SystemExit('must not run')")

    def test_build_output_requires_durable_evidence_and_same_checkout_head(self):
        head = self.finish()
        resource_id = "validation-build"
        tree = self.attempt(resource_id, "validation", head, "independent-validation")
        reference = self.build_output(resource_id, ["generated"], """
Path("generated").mkdir()
Path("generated/result").write_bytes(b"verified")
""")
        self.invoke("finish_worktree_attempt", resource_id=resource_id, report=self.attempt_report(resource_id))
        path = self.path / "reports" / reference["file"]
        saved = path.read_bytes()
        path.write_bytes(saved + b" ")
        with self.assertRaisesRegex(ValueError, "report changed"):
            self.cleanup_approval([resource_id])
        path.unlink()
        with self.assertRaisesRegex(ValueError, "Missing preserved"):
            self.cleanup_approval([resource_id])
        path.write_bytes(saved)
        self.git(tree, "commit", "--allow-empty", "-m", "Move validation checkout beyond the recorded build")
        with self.assertRaisesRegex(ValueError, "Build evidence does not match"):
            self.cleanup_approval([resource_id])

    @unittest.skipUnless(os.name == "nt", "Windows named stream behavior")
    def test_windows_named_streams_block_directory_and_file_output(self):
        self.finish()
        resource_id = "task-first"
        tree = self.path / "tasks/first"
        self.build_output(resource_id, ["generated"], """
Path("generated").mkdir()
Path("generated/result").write_bytes(b"verified default stream")
""")
        for relative in ("generated", "generated/result"):
            with self.subTest(path=relative):
                stream = Path(str(tree / relative) + ":unrecorded")
                stream.write_bytes(b"preserve separately authored data")
                try:
                    with self.assertRaisesRegex(ValueError, "Named Windows data stream retained"):
                        self.cleanup_approval([resource_id])
                    with self.assertRaisesRegex(ValueError, "Named Windows data stream retained"):
                        self.build_output(resource_id, ["generated"], "raise SystemExit('must not run')")
                    self.assertEqual(stream.read_bytes(), b"preserve separately authored data")
                finally:
                    stream.unlink()

        with self.assertRaisesRegex(ValueError, "Named Windows data stream retained"):
            self.build_output(resource_id, ["generated"], """
Path("generated/result:added by build").write_bytes(b"not inventoried")
""")
        self.assertEqual(len(self.read()["resources"][resource_id]["build_output"]["reports"]), 1)

    @unittest.skipUnless(os.name == "nt", "Windows named stream behavior")
    def test_windows_named_streams_block_approved_empty_output_cleanup(self):
        self.finish()
        resource_id = "task-first"
        tree = self.path / "tasks/first"
        (tree / "outside empty").mkdir()
        self.build_output(resource_id, ["generated"], "pass")
        authorized = self.cleanup_approval([resource_id])
        self.assertEqual(self.read()["cleanup"]["inventory"][0]["output_inventory"]["entries"], {})

        for entry in (tree, tree / "tracked.txt", tree / "outside empty", tree / ".git"):
            with self.subTest(path=entry.name):
                stream = Path(str(entry) + ":unrecorded")
                stream.write_bytes(b"retain")
                try:
                    result = self.invoke("cleanup_apply", authorized=authorized)
                    self.assertEqual(result["removed"], [])
                    self.assertIn("Named Windows data stream retained", result["blocked"][0]["error"])
                    self.assertEqual(stream.read_bytes(), b"retain")
                finally:
                    stream.unlink()

        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertEqual(result["removed"], [resource_id])
        self.assertEqual(result["blocked"], [])

    @unittest.skipUnless(os.name == "nt", "Windows named stream behavior")
    def test_windows_named_streams_block_validation_cleanup_without_build_evidence(self):
        resource_id = "validation-no-build"
        head = self.finish()
        tree = self.attempt(resource_id, "validation", head, "independent-validation")
        self.invoke("finish_worktree_attempt", resource_id=resource_id, report=self.attempt_report(resource_id))

        early_stream = Path(str(tree / "first.txt") + ":unrecorded")
        early_stream.write_bytes(b"retain before planning")
        try:
            with self.assertRaisesRegex(ValueError, "Named Windows data stream retained"):
                self.cleanup_approval([resource_id])
            self.assertEqual(early_stream.read_bytes(), b"retain before planning")
        finally:
            early_stream.unlink()

        authorized = self.cleanup_approval([resource_id])
        snapshot = self.read()["cleanup"]["inventory"][0]
        self.assertNotIn("build_output", snapshot)
        self.assertNotIn("output_inventory", snapshot)
        root_stream = Path(str(tree) + ":unrecorded")
        root_stream.write_bytes(b"retain after planning")
        try:
            result = self.invoke("cleanup_apply", authorized=authorized)
            self.assertEqual(result["removed"], [])
            self.assertIn("Named Windows data stream retained", result["blocked"][0]["error"])
            self.assertEqual(root_stream.read_bytes(), b"retain after planning")
        finally:
            root_stream.unlink()

        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertEqual(result["removed"], [resource_id])
        self.assertEqual(result["blocked"], [])
        self.assertEqual(self.read()["cleanup"]["inventory"], [snapshot])

    @unittest.skipUnless(os.name == "nt", "Windows named stream behavior")
    def test_windows_unavailable_stream_enumeration_blocks_capture(self):
        self.finish()
        resource_id = "task-first"
        for error in (5, 87):
            with self.subTest(error=error), patch.object(
                    workflow, "find_first_stream", return_value=workflow.INVALID_STREAM_HANDLE), patch.object(
                    workflow.ctypes, "get_last_error", return_value=error):
                with self.assertRaisesRegex(ValueError, "Cannot verify Windows data streams"):
                    self.build_output(resource_id, ["generated"], "raise SystemExit('must not run')")
        self.assertNotIn("build_output", self.read()["resources"][resource_id])

    def create_output_cleanup(self):
        self.finish()
        tree = self.path / "tasks/first"
        self.build_output("task-first", ["generated"], """
Path("generated/nested empty").mkdir(parents=True)
Path("generated/first").write_bytes(b"first")
Path("generated/second").write_bytes(b"second")
""")
        return tree, self.cleanup_approval(["task-first"])

    def test_verified_output_cleanup_rechecks_and_removes_approved_entries(self):
        tree, authorized = self.create_output_cleanup()
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertEqual(result["blocked"], [])
        self.assertEqual(result["removed"], ["task-first"])
        self.assertFalse(tree.exists())
        state = self.read()
        item = state["cleanup"]["items"][0]
        self.assertEqual(item["removed_output"], [
            "generated/first", "generated/nested empty", "generated/second", "generated",
        ])
        self.assertEqual(state["cleanup"]["inventory"][0]["head"],
                         self.git(self.repo, "rev-parse", result["recovery_refs"][0]))

    def test_verified_output_resume_after_unlink_preserves_existing_approval(self):
        tree, authorized = self.create_output_cleanup()
        original = workflow.Workspace.remove_output_entry

        def interrupt_after_unlink(workspace, path, output, name, quarantine=None):
            original(workspace, path, output, name, quarantine)
            raise OSError("interrupted after deleting one approved path")

        with patch.object(workflow.Workspace, "remove_output_entry", interrupt_after_unlink):
            result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertEqual(result["blocked"][0]["error"], "interrupted after deleting one approved path")
        self.assertEqual(result["recovery_refs"], ["refs/feature-workflow/sample/task-first"])
        self.assertFalse((tree / "generated/first").exists())
        self.assertEqual(self.read()["cleanup"]["items"][0]["removing_output"], "generated/first")
        self.assertTrue((tree / "generated/second").exists())

        # Recreating a removed file, even with matching bytes, cannot acquire the approval.
        restored = tree / "generated/first"
        restored.write_bytes(b"first")
        blocked = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("Build output contents changed", blocked["blocked"][0]["error"])
        self.assertTrue(restored.exists())
        restored.unlink()
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertEqual(result["removed"], ["task-first"])
        self.assertEqual(result["blocked"], [])

    def test_verified_output_rejects_same_bytes_replacement_at_removal_boundary(self):
        tree, authorized = self.create_output_cleanup()
        target = tree / "generated/first"
        original = workflow.Workspace.remove_output_entry

        def substitute(workspace, path, output, name, quarantine=None):
            # Keep the original alive so the replacement cannot reuse its filesystem ID.
            target.rename(tree / "generated/moved")
            target.write_bytes(b"first")
            original(workspace, path, output, name, quarantine)

        with patch.object(workflow.Workspace, "remove_output_entry", substitute):
            result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("Build output entry changed", result["blocked"][0]["error"])
        self.assertEqual(target.read_bytes(), b"first")
        self.assertEqual((tree / "generated/moved").read_bytes(), b"first")

    def test_verified_output_stops_after_branch_moves_mid_removal(self):
        tree, authorized = self.create_output_cleanup()
        state = self.read()
        expected = state["tasks"]["first"]["head"]
        branch = "refs/heads/" + state["tasks"]["first"]["branch"]
        moved_head = state["integrated_head"]
        original = workflow.Workspace.remove_output_entry

        def move_branch_after_first_output(workspace, path, output, name, quarantine=None):
            original(workspace, path, output, name, quarantine)
            self.git(self.repo, "update-ref", branch, moved_head, expected)

        with patch.object(workflow.Workspace, "remove_output_entry", move_branch_after_first_output):
            result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("branch or HEAD changed", result["blocked"][0]["error"])
        self.assertFalse((tree / "generated/first").exists())
        self.assertTrue((tree / "generated/second").exists())
        self.assertEqual(self.git(self.repo, "rev-parse", branch), moved_head)
        self.assertEqual(self.git(self.repo, "rev-parse", result["recovery_refs"][0]), expected)
        self.git(self.repo, "update-ref", branch, expected, moved_head)
        self.assertEqual(self.invoke("cleanup_apply", authorized=authorized)["removed"], ["task-first"])

    def test_verified_output_cleanup_blocks_unjournaled_missing_entries(self):
        tree, authorized = self.create_output_cleanup()
        (tree / "generated/second").unlink()
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("Build output contents changed", result["blocked"][0]["error"])
        self.assertTrue((tree / "generated/first").exists())
        self.assertEqual(result["recovery_refs"], [])

    def test_cleanup_inventory_replacement_preserves_prior_approval_and_requires_new_digest(self):
        tree, authorized = self.create_output_cleanup()
        self.build_output("task-first", ["generated"], """
Path("generated/second").write_bytes(b"rebuilt by a recorded build")
""")
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("Resource inventory changed", result["blocked"][0]["error"])
        old = self.read()["cleanup"]
        self.assertEqual((tree / "generated/second").read_bytes(), b"rebuilt by a recorded build")
        with self.assertRaisesRegex(ValueError, "exact inventory to replace"):
            self.invoke("cleanup_plan", resource_ids=["task-first"], replaces_inventory_sha256="wrong")
        plan = self.invoke("cleanup_plan", resource_ids=["task-first"],
                           replaces_inventory_sha256=authorized["inventory_sha256"])
        self.assertNotEqual(plan["inventory_sha256"], authorized["inventory_sha256"])
        archive, = (self.path / "reports").glob("cleanup-inventory-*.json")
        previous = json.loads(archive.read_text(encoding="utf-8"))
        self.assertEqual(previous, dict(plan=old, authorization=authorized))
        with self.assertRaisesRegex(ValueError, "Exact inventory approval"):
            self.invoke("cleanup_apply", authorized=authorized)
        self.assertTrue(tree.exists())
        renewed = dict(authorized, inventory_sha256=plan["inventory_sha256"])
        self.assertEqual(self.invoke("cleanup_apply", authorized=renewed)["blocked"], [])

    def test_partial_output_cleanup_cannot_discard_journal_or_overwrite_ref(self):
        tree, authorized = self.create_output_cleanup()
        ref = "refs/feature-workflow/sample/task-first"
        old = self.read()
        wrong_head = old["integrated_head"]
        expected = old["tasks"]["first"]["head"]
        self.git(self.repo, "update-ref", ref, wrong_head)
        blocked = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("Recovery ref does not match", blocked["blocked"][0]["error"])
        self.assertEqual(self.git(self.repo, "rev-parse", ref), wrong_head)
        self.assertTrue((tree / "generated/first").exists())
        self.git(self.repo, "update-ref", "-d", ref, wrong_head)

        with patch.object(workflow.Workspace, "remove_output_entry", side_effect=OSError("blocked output")):
            self.assertIn("blocked output", self.invoke("cleanup_apply", authorized=authorized)["blocked"][0]["error"])
        self.assertEqual(self.git(self.repo, "rev-parse", ref), expected)
        with self.assertRaisesRegex(ValueError, "every partially removed resource"):
            resource_id = "temporary"
            directory = self.path / resource_id
            directory.mkdir()
            self.invoke("register_resource", resource_id=resource_id, kind="directory", owner="fixture",
                        purpose="scratch", path=str(directory))
            self.invoke("cleanup_plan", resource_ids=[resource_id],
                        replaces_inventory_sha256=authorized["inventory_sha256"])
        self.git(self.repo, "update-ref", ref, wrong_head, expected)
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("Missing or changed recovery ref", result["blocked"][0]["error"])
        self.assertTrue((tree / "generated/first").exists())
        self.assertEqual(self.git(self.repo, "rev-parse", ref), wrong_head)

    def test_inventory_replacement_carries_unchanged_partial_output_journal(self):
        tree, approved = self.create_output_cleanup()
        original = workflow.Workspace.remove_output_entry

        def interrupt_after_unlink(workspace, path, output, name, quarantine=None):
            original(workspace, path, output, name, quarantine)
            raise OSError("interrupted after deleting one approved path")

        with patch.object(workflow.Workspace, "remove_output_entry", interrupt_after_unlink):
            self.assertTrue(self.invoke("cleanup_apply", authorized=approved)["blocked"])
        self.assertFalse((tree / "generated/first").exists())
        old = self.read()["cleanup"]
        new_directory = self.path / "additional temporary"
        new_directory.mkdir()
        self.invoke("register_resource", resource_id="additional", kind="directory", owner="fixture",
                    purpose="scratch", path=str(new_directory))
        renewed = self.invoke("cleanup_plan", resource_ids=["task-first", "additional"],
                              replaces_inventory_sha256=old["inventory_sha256"])
        self.assertEqual(renewed["items"][0], old["items"][0])
        self.assertNotEqual(renewed["inventory_sha256"], approved["inventory_sha256"])
        with self.assertRaisesRegex(ValueError, "Exact inventory approval"):
            self.invoke("cleanup_apply", authorized=approved)
        result = self.invoke("cleanup_apply", authorized=dict(approved, inventory_sha256=renewed["inventory_sha256"]))
        self.assertEqual(result["removed"], ["task-first", "additional"])
        self.assertEqual(result["blocked"], [])

    def test_cleanup_resumes_if_git_removed_worktree_before_reporting_failure(self):
        tree, authorized = self.create_output_cleanup()
        original_git = workflow.git

        def interrupted(repo, *args, **kwargs):
            result = original_git(repo, *args, **kwargs)
            if args[:2] == ("worktree", "remove"):
                raise OSError("interrupted after worktree removal")
            return result

        with patch.object(workflow, "git", side_effect=interrupted):
            result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("interrupted after worktree removal", result["blocked"][0]["error"])
        self.assertFalse(tree.exists())
        self.assertTrue(self.read()["cleanup"]["items"][0]["worktree_removing"])
        self.assertEqual(self.invoke("cleanup_apply", authorized=authorized)["removed"], ["task-first"])

    def test_branch_checked_out_elsewhere_after_worktree_removal_is_retained(self):
        tree, authorized = self.create_output_cleanup()
        original_git = workflow.git

        def interrupted(repo, *args, **kwargs):
            result = original_git(repo, *args, **kwargs)
            if args[:2] == ("worktree", "remove"):
                raise OSError("interrupted before branch removal")
            return result

        with patch.object(workflow, "git", side_effect=interrupted):
            self.assertTrue(self.invoke("cleanup_apply", authorized=authorized)["blocked"])
        self.assertFalse(tree.exists())
        alternate = self.path / "alternate checkout"
        branch = self.read()["tasks"]["first"]["branch"]
        self.git(self.repo, "worktree", "add", str(alternate), branch)
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("checked out in another worktree", result["blocked"][0]["error"])
        self.assertTrue(alternate.exists())
        self.assertEqual(self.git(self.repo, "rev-parse", branch),
                         self.git(self.repo, "rev-parse", result["recovery_refs"][0]))

    def test_cleanup_rechecks_branch_occupancy_under_the_expected_ref_lock(self):
        self.finish()
        authorized = self.cleanup_approval(["task-first"])
        tree = self.path / "tasks/first"
        alternate = self.path / "alternate during first listing"
        state = self.read()
        branch = state["tasks"]["first"]["branch"]
        expected = state["tasks"]["first"]["head"]
        original = workflow.Workspace.cleanup_branch_in_use

        def attach_after_first_listing(workspace, ref):
            result = original(workspace, ref)
            if not tree.exists() and not alternate.exists():
                self.git(self.repo, "worktree", "add", str(alternate), branch)
            return result

        with patch.object(workflow.Workspace, "cleanup_branch_in_use", attach_after_first_listing):
            result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("checked out in another worktree", result["blocked"][0]["error"])
        self.assertEqual(self.git(alternate, "rev-parse", "HEAD"), expected)
        self.assertEqual(self.git(self.repo, "rev-parse", branch), expected)

    def test_native_worktree_add_cannot_attach_to_the_locked_branch(self):
        self.finish()
        authorized = self.cleanup_approval(["task-first"])
        alternate = self.path / "alternate during locked listing"
        state = self.read()
        branch = state["tasks"]["first"]["branch"]
        original = workflow.Workspace.cleanup_branch_in_use
        attempts = []

        def attach_after_locked_listing(workspace, ref):
            result = original(workspace, ref)
            if self.read()["cleanup"]["items"][0].get("branch_removing") and not attempts:
                attempts.append(subprocess.run(["git", "-C", str(self.repo), "worktree", "add", str(alternate), branch],
                                               text=True, capture_output=True, timeout=15))
            return result

        with patch.object(workflow.Workspace, "cleanup_branch_in_use", attach_after_locked_listing):
            result = self.invoke("cleanup_apply", authorized=authorized)
        attempt, = attempts
        self.assertNotEqual(attempt.returncode, 0)
        self.assertIn("cannot lock ref", attempt.stderr)
        self.assertFalse(alternate.exists())
        self.assertEqual(result["removed"], ["task-first"])

    def test_branch_attached_after_transaction_commit_is_recovered_on_resume(self):
        self.finish()
        authorized = self.cleanup_approval(["task-first"])
        alternate = self.path / "alternate detached checkout"
        state = self.read()
        branch = "refs/heads/" + state["tasks"]["first"]["branch"]
        expected = state["tasks"]["first"]["head"]
        self.git(self.repo, "worktree", "add", "--detach", str(alternate), expected)
        original = workflow.Workspace.commit_branch_deletion

        def interrupt_after_head_attachment(workspace, ref, recovery, expected_head):
            original(workspace, ref, recovery, expected_head)
            # Simulate an independent writer attaching HEAD after ref locks were released.
            self.git(alternate, "symbolic-ref", "HEAD", branch)
            raise OSError("interrupted after branch transaction commit")

        with patch.object(workflow.Workspace, "commit_branch_deletion", interrupt_after_head_attachment):
            result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("interrupted after branch transaction commit", result["blocked"][0]["error"])
        self.assertTrue(alternate.exists())
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("restored its approved tip", result["blocked"][0]["error"])
        self.assertEqual(self.git(alternate, "rev-parse", "HEAD"), expected)
        self.assertEqual(self.git(self.repo, "rev-parse", result["recovery_refs"][0]), expected)

    def test_no_build_cleanup_rejects_tracked_changes_hidden_by_index_flags(self):
        head = self.finish()
        resource_id = "validation-hidden-tracked"
        tree = self.attempt(resource_id, "validation", head, "independent-validation")
        self.invoke("finish_worktree_attempt", resource_id=resource_id, report=self.attempt_report(resource_id))
        authorized = self.cleanup_approval([resource_id])
        tracked = tree / "first.txt"
        original = tracked.read_bytes()
        for flag in ("assume-unchanged", "skip-worktree"):
            with self.subTest(flag=flag):
                self.git(tree, "update-index", "--" + flag, "--", tracked.name)
                tracked.write_bytes(b"unrecorded local tracked changes")
                self.assertEqual(self.git(tree, "status", "--porcelain"), "")
                result = self.invoke("cleanup_apply", authorized=authorized)
                self.assertIn("Index flags can conceal", result["blocked"][0]["error"])
                self.assertEqual(tracked.read_bytes(), b"unrecorded local tracked changes")
                self.assertEqual(result["recovery_refs"], [])
                tracked.write_bytes(original)
                self.git(tree, "update-index", "--no-" + flag, "--", tracked.name)
        self.assertEqual(self.invoke("cleanup_apply", authorized=authorized)["removed"], [resource_id])

    @unittest.skipIf(os.name == "nt", "POSIX dirfd capture requires a native POSIX filesystem")
    def test_posix_substitution_at_atomic_capture_preserves_unknown_content(self):
        tree, authorized = self.create_output_cleanup()
        target = tree / "generated/first"
        original = self.path / "original still preserved"
        rename = os.rename

        def substitute_before_rename(src, dst, **kwargs):
            if src == target.name and dst == "entry" and "src_dir_fd" in kwargs:
                rename(target, original)
                target.write_bytes(b"unapproved replacement")
            return rename(src, dst, **kwargs)

        with patch.object(workflow.os, "rename", side_effect=substitute_before_rename):
            result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("Unapproved output preserved", result["blocked"][0]["error"])
        quarantine = Path(result["blocked"][0]["output_quarantine"]["path"])
        self.assertEqual((quarantine / "entry").read_bytes(), b"unapproved replacement")
        self.assertEqual(original.read_bytes(), b"first")
        self.assertTrue((tree / "generated/second").exists())
        result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertTrue(result["blocked"])
        self.assertEqual((quarantine / "entry").read_bytes(), b"unapproved replacement")

    @unittest.skipIf(os.name == "nt", "POSIX dirfd capture requires a native POSIX filesystem")
    def test_posix_verified_capture_resumes_after_interruption_before_unlink(self):
        tree, authorized = self.create_output_cleanup()
        rename = os.rename

        def interrupt_after_capture(src, dst, **kwargs):
            result = rename(src, dst, **kwargs)
            if src == "first" and dst == "entry" and "src_dir_fd" in kwargs:
                raise OSError("interrupted after capturing the approved output")
            return result

        with patch.object(workflow.os, "rename", side_effect=interrupt_after_capture):
            result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("interrupted after capturing", result["blocked"][0]["error"])
        quarantine = Path(result["blocked"][0]["output_quarantine"]["path"])
        self.assertEqual((quarantine / "entry").read_bytes(), b"first")
        self.assertFalse((tree / "generated/first").exists())
        self.assertEqual(self.invoke("cleanup_apply", authorized=authorized)["removed"], ["task-first"])
        self.assertFalse(quarantine.exists())

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
        with patch.object(workflow.Workspace, "commit_branch_deletion",
                          side_effect=OSError("interrupted branch removal")):
            result = self.invoke("cleanup_apply", authorized=authorized)
        self.assertIn("interrupted branch removal", result["blocked"][0]["error"])
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
