#!/usr/bin/env python3
"""Cooperative feature workflow safety helpers. Standard library; no network calls."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

VERSION = "1.1.0"
SCHEMA = 2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], text=True,
                            encoding="utf-8", capture_output=True)
    require(result.returncode == 0, result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def inside(path, parent):
    return Path(path).resolve().is_relative_to(Path(parent).resolve())


def identifier(value):
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", value) is not None,
            "Use a lowercase alphanumeric/hyphen identifier, at most 48 characters")
    return value


def approval(value):
    require(isinstance(value, dict) and all(value.get(k) for k in
            ("human", "evidence", "date")), "Explicit human approval evidence required")
    return value


def external(repo, path):
    path = Path(path).resolve()
    for line in git(repo, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            require(not inside(path, line[9:]), "Workspace must be outside all repository worktrees")
    # Also reject another repository, including ignored directories inside one.
    probe = path
    while not probe.exists():
        probe = probe.parent
    result = subprocess.run(["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
                            capture_output=True)
    require(result.returncode != 0, "Workspace must be outside any Git checkout")
    return path


def new_worktree(repo, destination, branch, base):
    require(not Path(destination).exists(), "Worktree destination already exists")
    git(repo, "check-ref-format", "--branch", branch)
    result = subprocess.run(["git", "-C", str(repo), "show-ref", "--verify", "--quiet",
                             "refs/heads/" + branch], capture_output=True)
    require(result.returncode == 1, "Branch exists or cannot be checked")
    git(repo, "worktree", "add", "-b", branch, str(destination), base)


def initialize(repo, workspace, feature_id, ticket, spec, approved, base="HEAD"):
    repo = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    require(Path(workspace).is_absolute(), "Absolute workspace required")
    workspace = external(repo, workspace)
    identifier(feature_id)
    approval(approved)
    require(not workspace.exists(), "Feature workspace already exists")
    commit = git(repo, "rev-parse", "--verify", base + "^{commit}")
    for filename in ("AGENTS.md", "GLOSSARY.md"):
        git(repo, "cat-file", "-e", commit + ":" + filename)
    # Read inputs before reserving the destination; no partial copy from missing inputs.
    ticket_bytes, spec_bytes = Path(ticket).read_bytes(), Path(spec).read_bytes()
    original = {"branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
                "head": git(repo, "rev-parse", "HEAD"),
                "status": git(repo, "status", "--porcelain=v1", "--untracked-files=all")}
    workspace.mkdir(parents=True, exist_ok=False)
    for name in ("specs", "reports", "decisions", "checkpoints", "tasks"):
        (workspace / name).mkdir()
    (workspace / "ticket.md").write_bytes(ticket_bytes)
    (workspace / "specs/0001.md").write_bytes(spec_bytes)
    branch = "codex/" + feature_id
    state = dict(schema_version=SCHEMA, library_version=VERSION, feature_id=feature_id,
                 repo=str(repo), original=original, feature_branch=branch,
                 feature_worktree=str(workspace / "feature"), base_commit=commit,
                 integrated_head=commit,
                 ticket_sha256=digest(workspace / "ticket.md"), spec_revision=1,
                 spec_sha256=digest(workspace / "specs/0001.md"),
                 spec_approval=dict(approved, revision=1, sha256=digest(workspace / "specs/0001.md")),
                 tasks={}, gates={}, integration=None, pr=None,
                 cleanup_authorization=None, lifecycle="active", merge=None,
                 resources={}, cleanup=None, generation=0)
    state["resources"]["feature"] = dict(kind="worktree", path=state["feature_worktree"],
        branch=branch, owner=feature_id, purpose="feature", task_id=None, status="creating")
    atomic_json(workspace / "checkpoints/initialization.json", state)
    new_worktree(repo, workspace / "feature", branch, commit)
    state["resources"]["feature"]["status"] = "present"
    atomic_json(workspace / "state.json", state)
    return state


class Workspace:
    def __init__(self, path, actor, role):
        self.path = Path(path).resolve()
        self.actor, self.role = actor, role
        require(bool(actor), "Actor identity required")

    @contextmanager
    def transaction(self):
        lock = self.path / ".workflow.lock"
        # Exclusive creation; never automatically break a stale lock.
        with lock.open("x", encoding="utf-8") as stream:
            json.dump({"actor": self.actor, "role": self.role, "pid": os.getpid()}, stream)
        try:
            self.state = json.loads((self.path / "state.json").read_text(encoding="utf-8"))
            require(self.state["schema_version"] == SCHEMA and
                    self.state["library_version"].split(".")[0] == VERSION.split(".")[0],
                    "Incompatible workspace; invoke manual Library Update")
            require(digest(self.path / "ticket.md") == self.state["ticket_sha256"],
                    "Original ticket changed")
            require(digest(self.spec_path()) == self.state["spec_sha256"], "Specification changed")
            require(self.state["spec_approval"].get("revision") == self.state["spec_revision"] and
                    self.state["spec_approval"].get("sha256") == self.state["spec_sha256"],
                    "Approval does not match specification")
            yield self
            self.state["generation"] += 1
            atomic_json(self.path / "state.json", self.state)
        finally:
            lock.unlink()

    def spec_path(self):
        return self.path / "specs" / ("%04d.md" % self.state["spec_revision"])

    def only(self, *roles):
        require(self.role in roles, "Operation requires role: " + ", ".join(roles))

    def feature_head(self, expected=True):
        tree = self.state["feature_worktree"]
        require(git(tree, "symbolic-ref", "--short", "HEAD") == self.state["feature_branch"],
                "Feature worktree branch mismatch")
        require(not git(tree, "status", "--porcelain"), "Feature worktree must be clean")
        head = git(tree, "rev-parse", "HEAD")
        if expected:
            require(head == self.state["integrated_head"], "Unexpected/stale feature HEAD; reconcile Git evidence")
        return head

    def invalidate(self):
        self.state["gates"] = {}

    def add_task(self, task_id, depends_on, scope, acceptance_ids, tests):
        self.only("planner", "orchestrator")
        require(self.state["lifecycle"] in ("active", "published"), "Feature already merged")
        identifier(task_id)
        require(task_id not in self.state["tasks"], "Task already exists")
        require(scope and acceptance_ids and tests, "Scope, acceptance IDs and tests required")
        require(isinstance(tests, list) and all(isinstance(c, list) and c and
                all(isinstance(a, str) for a in c) for c in tests), "Tests must be argument arrays")
        require(len(depends_on) == len(set(depends_on)), "Duplicate dependencies")
        require(all(d in self.state["tasks"] for d in depends_on),
                "Add dependencies first; missing dependencies/cycles rejected")
        self.state["tasks"][task_id] = dict(status="pending", depends_on=depends_on,
            scope=scope, acceptance_ids=acceptance_ids, tests=tests, owner=None, branch=None,
            worktree=None, base_commit=None, head=None, review=None, integration_commit=None)

    def start_task(self, task_id, owner):
        self.only("orchestrator")
        task = self.state["tasks"][task_id]
        require(task["status"] == "pending", "Task must be pending")
        require(owner, "Implementer identity required")
        require(all(self.state["tasks"][d]["status"] == "complete" for d in task["depends_on"]),
                "Dependencies incomplete")
        head = self.feature_head()
        # Git cannot have both refs/heads/codex/x and codex/x/task.
        branch = "codex/" + self.state["feature_id"] + "-task-" + task_id
        destination = self.path / "tasks" / task_id
        self.state["resources"]["task-" + task_id] = dict(kind="worktree", path=str(destination),
            branch=branch, owner=owner, purpose="task", task_id=task_id, status="creating")
        atomic_json(self.path / "state.json", self.state)
        new_worktree(self.state["repo"], destination, branch, head)
        self.state["resources"]["task-" + task_id]["status"] = "present"
        task.update(status="implementing", owner=owner, branch=branch,
                    worktree=str(destination), base_commit=head)

    def submit(self, task_id):
        self.only("orchestrator")
        task = self.state["tasks"][task_id]
        require(task["status"] == "implementing", "Task must be implementing")
        require(not git(task["worktree"], "status", "--porcelain"), "Task tree must be clean")
        require(git(task["worktree"], "symbolic-ref", "--short", "HEAD") == task["branch"],
                "Task branch mismatch")
        head = git(task["worktree"], "rev-parse", "HEAD")
        require(head != task["base_commit"], "Task has no commit")
        task.update(status="review", head=head, review=None)

    def review(self, task_id, report):
        self.only("orchestrator")
        task = self.state["tasks"][task_id]
        require(task["status"] == "review", "Task must await review")
        require(report.get("agent") and report["agent"] != task["owner"], "Independent reviewer required")
        require(report.get("head") == task["head"] and
                report.get("spec_revision") == self.state["spec_revision"], "Stale review")
        require(report.get("tests") and "findings" in report, "Review evidence required")
        require(report.get("verdict") in ("pass", "fail"), "Review verdict required")
        self.save_report("review-" + task_id, report)
        task["review"] = report
        task["status"] = "reviewed" if report["verdict"] == "pass" else "implementing"

    def return_task(self, task_id, reason):
        self.only("orchestrator")
        require(not self.state["integration"], "Reconcile integration before returning task")
        task = self.state["tasks"][task_id]
        require(task["status"] in ("implementing", "review", "reviewed"),
                "Only unfinished dispatched tasks can return for repair")
        require(reason, "Repair reason/evidence required")
        self.save_report("return-" + task_id, dict(agent=self.actor, reason=reason,
                         previous_head=task["head"], spec_revision=self.state["spec_revision"]))
        task.update(status="implementing", head=None, review=None)

    def save_report(self, prefix, report):
        target = self.path / "reports" / (prefix + "-" + str(self.state["generation"]) + ".json")
        require(not target.exists(), "Report exists; reconcile interrupted operation")
        atomic_json(target, report)
        return str(target)

    def integrate(self, task_id):
        self.only("orchestrator")
        require(not self.state["integration"], "Unresolved integration checkpoint; reconcile Git first")
        task = self.state["tasks"][task_id]
        require(task["status"] == "reviewed", "Independent passing review required")
        review = task["review"]
        require(review["head"] == task["head"] and review["spec_revision"] == self.state["spec_revision"],
                "Stale review")
        require(git(task["worktree"], "rev-parse", "HEAD") == task["head"] and
                not git(task["worktree"], "status", "--porcelain"), "Task changed after review")
        require(git(task["worktree"], "symbolic-ref", "--short", "HEAD") == task["branch"],
                "Task branch mismatch")
        require(all(self.state["tasks"][d]["status"] == "complete" for d in task["depends_on"]),
                "Dependencies incomplete")
        tree = self.state["feature_worktree"]
        before = self.feature_head()
        git(tree, "merge-base", "--is-ancestor", task["base_commit"], task["head"])
        git(tree, "merge-base", "--is-ancestor", task["base_commit"], before)
        intent = dict(task=task_id, source_head=task["head"], parent=before,
                      spec_revision=self.state["spec_revision"], phase="prepared")
        self.state["integration"] = intent
        # Persist intent BEFORE mutation; failures intentionally leave a blocking checkpoint.
        atomic_json(self.path / "state.json", self.state)
        atomic_json(self.path / "checkpoints" / ("integration-" + str(self.state["generation"]) + ".json"), intent)
        git(tree, "merge", "--squash", "--", task["head"])
        require(git(tree, "diff", "--cached", "--stat"), "Empty squash; investigate duplicate integration")
        expected_tree = git(tree, "write-tree")
        test_results = self.run_tests(task, tree)
        require(git(tree, "write-tree") == expected_tree and not git(tree, "diff", "--name-only") and
                not git(tree, "ls-files", "--others", "--exclude-standard"),
                "Integrated checks changed files; inspect checkpoint before repair")
        message = ("Integrate " + task_id + "\n\nFeature: " + self.state["feature_id"] +
                   "\nTask: " + task_id + "\nSource-Head: " + task["head"] +
                   "\nSpec-Revision: " + str(self.state["spec_revision"]))
        intent.update(tree=expected_tree, tests=test_results)
        atomic_json(self.path / "state.json", self.state)
        git(tree, "commit", "-m", message)
        commit = git(tree, "rev-parse", "HEAD")
        require(git(tree, "rev-parse", "HEAD^") == before and
                git(tree, "rev-parse", "HEAD^{tree}") == expected_tree, "Unexpected integration commit")
        require(not git(tree, "status", "--porcelain"), "Commit left dirty feature worktree")
        task.update(status="complete", integration_commit=commit)
        self.state["integrated_head"] = commit
        intent.update(phase="committed", commit=commit, tree=expected_tree)
        task["integration_evidence"] = dict(intent)
        atomic_json(self.path / "checkpoints" / ("result-" + str(self.state["generation"]) + ".json"), intent)
        self.state["integration"] = None
        self.invalidate()
        return commit

    def run_tests(self, task, tree):
        results = []
        for command in task["tests"]:
            try:
                result = subprocess.run(command, cwd=tree, text=True, encoding="utf-8",
                                        capture_output=True, timeout=600)
            except (OSError, subprocess.TimeoutExpired) as error:
                results.append(dict(command=command, exit_code=None, error=str(error)))
                atomic_json(self.path / "checkpoints" / ("checks-" + str(self.state["generation"]) + ".json"), results)
                raise ValueError("Integrated task checks could not finish; preserve checkpoint") from error
            results.append(dict(command=command, exit_code=result.returncode,
                                stdout=result.stdout, stderr=result.stderr))
            atomic_json(self.path / "checkpoints" / ("checks-" + str(self.state["generation"]) + ".json"), results)
            require(result.returncode == 0, "Integrated task checks failed; preserve checkpoint and repair")
        return results

    def recover(self):
        self.only("orchestrator")
        intent = self.state["integration"]
        require(intent, "No integration checkpoint to reconcile")
        tree = self.state["feature_worktree"]
        head = self.feature_head(expected=False)
        if head == intent["parent"]:
            # Clean unchanged Git proves no pending squash or commit remains.
            self.state["integration"] = None
            return {"recovered": "no-mutation", "head": head}
        require(intent.get("tree") and intent.get("tests"), "Missing prepared tree/test evidence")
        require(git(tree, "rev-parse", "HEAD^") == intent["parent"] and
                git(tree, "rev-parse", "HEAD^{tree}") == intent["tree"], "Ambiguous integration commit")
        message = git(tree, "log", "-1", "--format=%B")
        for trailer in ("Feature: " + self.state["feature_id"], "Task: " + intent["task"],
                        "Source-Head: " + intent["source_head"],
                        "Spec-Revision: " + str(intent["spec_revision"])):
            require(trailer in message.splitlines(), "Commit trailers mismatch")
        require(intent["spec_revision"] == self.state["spec_revision"], "Recovery spec mismatch")
        task = self.state["tasks"][intent["task"]]
        self.run_tests(task, tree)
        require(self.feature_head(expected=False) == head and git(tree, "rev-parse", "HEAD^{tree}") == intent["tree"],
                "Recovery checks changed feature worktree")
        task.update(status="complete", integration_commit=head)
        task["integration_evidence"] = dict(intent, phase="committed", commit=head)
        self.state["integrated_head"] = head
        self.state["integration"] = None
        self.invalidate()
        return {"recovered": "committed", "head": head}

    def revise(self, spec, approved, affected_tasks):
        self.only("orchestrator")
        approval(approved)
        require(not self.state["integration"], "Resolve integration before requirements change")
        require(all(t in self.state["tasks"] for t in affected_tasks), "Unknown affected task")
        # Integrated work remains historical; corrections are new dependent tasks.
        require(all(self.state["tasks"][t]["status"] != "complete" for t in affected_tasks),
                "Completed tasks require new corrective tasks, not history rewriting")
        data = Path(spec).read_bytes()
        next_revision = self.state["spec_revision"] + 1
        path = self.path / "specs" / ("%04d.md" % next_revision)
        with path.open("xb") as stream:
            stream.write(data)
        self.state.update(spec_revision=next_revision, spec_sha256=digest(path),
                          spec_approval=dict(approved, revision=next_revision, sha256=digest(path)))
        for task_id, task in self.state["tasks"].items():
            if task["status"] == "complete":
                continue
            task["review"] = None
            if task["status"] in ("review", "reviewed"):
                # Unchanged code still needs a current-revision independent review.
                task["status"] = "implementing" if task_id in affected_tasks else "review"
        self.invalidate()

    def gate(self, kind, report):
        self.only("orchestrator")
        require(kind in ("validation", "quality"), "Unknown gate")
        require(self.state["tasks"] and all(t["status"] == "complete" for t in self.state["tasks"].values()),
                "All tasks must be complete")
        require(report.get("head") == self.feature_head() and
                report.get("spec_revision") == self.state["spec_revision"], "Stale gate")
        require(report.get("agent") and report["agent"] not in
                {t["owner"] for t in self.state["tasks"].values()}, "Independent gate agent required")
        require(type(report.get("passed")) is bool and report.get("evidence"), "Gate evidence required")
        path = self.save_report(kind, report)
        self.state["gates"][kind] = dict(report, report=path)

    def pr_ready(self):
        self.only("orchestrator")
        require(not self.state["integration"], "Unresolved integration")
        require(self.state["tasks"] and all(t["status"] == "complete" for t in self.state["tasks"].values()),
                "Incomplete tasks")
        head = self.feature_head()
        for kind in ("validation", "quality"):
            gate = self.state["gates"].get(kind, {})
            require(gate.get("passed") is True and gate.get("head") == head and
                    gate.get("spec_revision") == self.state["spec_revision"], "Missing/stale " + kind + " gate")
        return {"ready": True, "head": head, "draft_only": True}

    def record_pr(self, url, head, base, evidence, merge_commit=None):
        """Record inspected service evidence; this helper never merges or polls a PR."""
        self.only("orchestrator")
        require(url and base and evidence, "PR URL, base and inspected service evidence required")
        require(head == self.state["integrated_head"], "PR head mismatch")
        require(self.state["lifecycle"] not in ("merged", "cleanup_pending", "closed"), "Already merged")
        if merge_commit:
            require(self.state["pr"] and self.state["pr"]["url"] == url and
                    self.state["pr"]["head"] == head and self.state["pr"]["base"] == base,
                    "Record matching publication first")
            repo = self.state["repo"]
            commit = git(repo, "rev-parse", "--verify", merge_commit + "^{commit}")
            git(repo, "merge-base", "--is-ancestor", commit, base)
            # Squash/rebase evidence: the merged tree must match the published tree.
            # A normal merge can instead prove source ancestry.
            ancestor = subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", head, commit],
                                      capture_output=True).returncode == 0
            require(ancestor or git(repo, "rev-parse", commit + "^{tree}") ==
                    git(repo, "rev-parse", head + "^{tree}"), "Merge does not prove published contents")
            self.state["merge"] = dict(commit=commit, base=base, evidence=evidence, head=head)
            self.state["lifecycle"] = "merged"
        else:
            self.pr_ready()
            self.state["pr"] = dict(url=url, head=head, base=base, evidence=evidence)
            self.state["lifecycle"] = "published"

    def register_resource(self, resource_id, kind, owner, purpose, path=None, branch=None,
                          task_id=None, docker_id=None):
        self.only("orchestrator")
        identifier(resource_id)
        require(resource_id not in self.state["resources"], "Resource already recorded")
        require(kind in ("worktree", "directory", "container", "network") and owner and purpose,
                "Resource kind, owner and purpose required")
        require(self.state["lifecycle"] != "closed", "Feature closed")
        require((kind in ("worktree", "directory") and path and Path(path).is_absolute()) or
                (kind in ("container", "network") and docker_id and re.fullmatch(r"[a-f0-9]{64}", docker_id)),
                "Exact absolute path or full Docker ID required")
        self.state["resources"][resource_id] = dict(kind=kind, owner=owner, purpose=purpose,
            path=path, branch=branch, task_id=task_id, docker_id=docker_id, status="present")

    def docker(self, *args):
        result = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8")
        require(result.returncode == 0, result.stderr.strip() or "Docker operation failed")
        return result.stdout

    def inspect_resource(self, resource):
        r = dict(resource)
        require(not self.state["integration"], "Recovery evidence still needed")
        if r["kind"] in ("container", "network"):
            data = json.loads(self.docker(r["kind"], "inspect", r["docker_id"]))[0]
            labels = data.get("Config", {}).get("Labels", {}) if r["kind"] == "container" else data.get("Labels", {})
            require(data["Id"] == r["docker_id"] and labels and
                    labels.get("feature-workflow.feature") == self.state["feature_id"] and
                    labels.get("feature-workflow.owner") == r["owner"], "Docker ownership mismatch")
            require(not data.get("State", {}).get("Running") and not data.get("Containers"),
                    "Running application or shared network retained")
            return r
        raw = Path(r["path"])
        path = raw.resolve()
        require(raw.is_absolute() and path != self.path and inside(path, self.path) and
                path != Path(self.state["repo"]).resolve(), "Unsafe cleanup path")
        # Reject symlinks/junctions in any component, including Windows reparse points.
        for part in (raw, *raw.parents):
            if part == self.path.parent:
                break
            require(not part.is_symlink() and not (part.exists() and
                    getattr(part.lstat(), "st_file_attributes", 0) & 0x400), "Linked cleanup path")
        if r["kind"] == "directory":
            require(path.is_dir() and not any(path.iterdir()), "Unknown files retained; directory must be empty")
            return r
        require(r.get("branch"), "Worktree branch required")
        listing = git(self.state["repo"], "worktree", "list", "--porcelain")
        records = [block.splitlines() for block in listing.split("\n\n")]
        require(any(lines and lines[0].startswith("worktree ") and
                    Path(lines[0][9:]).resolve() == path and
                    "branch refs/heads/" + r["branch"] in lines for lines in records), "Worktree registration mismatch")
        require(not git(path, "status", "--porcelain", "--untracked-files=all", "--ignored"), "Dirty/ignored files retained")
        require(git(path, "symbolic-ref", "--short", "HEAD") == r["branch"], "Worktree branch mismatch")
        head = git(path, "rev-parse", "HEAD")
        if r["purpose"] == "feature":
            require(self.state["merge"] and head == self.state["merge"]["head"] and
                    r["path"] == self.state["feature_worktree"], "Feature requires verified PR merge")
        else:
            task = self.state["tasks"][r["task_id"]]
            require(task["status"] == "complete" and head == task["head"], "Unintegrated/changed source")
            if r["purpose"] == "task":
                require(r["path"] == task["worktree"] and r["branch"] == task["branch"] and
                        r["owner"] == task["owner"], "Task resource mismatch")
            commit = task["integration_commit"]
            proof = task.get("integration_evidence", {})
            require(proof.get("source_head") == head and proof.get("commit") == commit and
                    proof.get("tests") and all(t["exit_code"] == 0 for t in proof["tests"]) and
                    git(self.state["repo"], "rev-parse", commit + "^") == proof.get("parent") and
                    git(self.state["repo"], "rev-parse", commit + "^{tree}") == proof.get("tree"),
                    "Missing recorded integration tree/check evidence")
            git(self.state["repo"], "merge-base", "--is-ancestor", commit, self.state["integrated_head"])
            message = git(self.state["repo"], "log", "-1", "--format=%B", commit).splitlines()
            require("Source-Head: " + head in message and "Task: " + r["task_id"] in message and
                    "Feature: " + self.state["feature_id"] in message, "Missing squash integration evidence")
        r["head"] = head
        return r

    def cleanup_plan(self, resource_ids):
        self.only("orchestrator")
        require(resource_ids and len(resource_ids) == len(set(resource_ids)), "Unique inventory required")
        previous = self.state.get("cleanup")
        require(not previous or all(x["status"] == "removed" for x in previous["items"]),
                "Resume pending cleanup before replacing plan")
        inventory = [dict(resource_id=i, **self.inspect_resource(self.state["resources"][i])) for i in resource_ids]
        token = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
        self.state["cleanup"] = dict(inventory=inventory, inventory_sha256=token,
            items=[dict(resource_id=i, status="pending") for i in resource_ids])
        return self.state["cleanup"]

    def cleanup_apply(self, authorized):
        self.only("orchestrator")
        approval(authorized)
        plan = self.state["cleanup"]
        require(plan and authorized.get("feature_id") == self.state["feature_id"] and
                authorized.get("inventory_sha256") == plan["inventory_sha256"], "Exact inventory approval required")
        self.state["cleanup_authorization"] = authorized
        atomic_json(self.path / "checkpoints" / ("cleanup-" + str(self.state["generation"]) + ".json"),
                    dict(plan=plan, authorized=authorized, actor=self.actor))
        if self.state["merge"]:
            self.state["lifecycle"] = "cleanup_pending"
        for snapshot, item in zip(plan["inventory"], plan["items"]):
            if item["status"] == "removed":
                continue
            try:
                resource = self.state["resources"][item["resource_id"]]
                require(all(resource.get(k) == v for k, v in snapshot.items()
                            if k not in ("resource_id", "head")), "Resource inventory changed")
                repo = self.state["repo"]
                recovery_ref = "refs/feature-workflow/" + self.state["feature_id"] + "/" + item["resource_id"]
                if resource["kind"] == "worktree":
                    # Intent is durable before each mutation. An absent tree can only be
                    # reconciled when its preservation ref proves this execution started.
                    if item["status"] != "removing" or Path(resource["path"]).exists():
                        require(self.inspect_resource(resource) == {k: v for k, v in snapshot.items() if k != "resource_id"},
                                "Inventory changed; create a new approved plan")
                    else:
                        require(git(repo, "rev-parse", recovery_ref) == snapshot["head"], "Missing recovery ref")
                    git(repo, "update-ref", recovery_ref, snapshot["head"])
                elif item["status"] != "removing":
                    self.inspect_resource(resource)
                item["status"] = "removing"
                atomic_json(self.path / "state.json", self.state)
                if resource["kind"] == "worktree":
                    if Path(resource["path"]).exists():
                        self.inspect_resource(resource)
                        git(repo, "worktree", "remove", "--", resource["path"])
                    ref = "refs/heads/" + resource["branch"]
                    exists = subprocess.run(["git", "-C", repo, "show-ref", "--verify", "--quiet", ref], capture_output=True)
                    require(exists.returncode in (0, 1), "Cannot inspect branch")
                    if exists.returncode == 0:
                        require("branch " + ref not in git(repo, "worktree", "list", "--porcelain").splitlines(),
                                "Branch checked out in another worktree")
                        # CAS prevents removing a concurrently advanced branch, including squash sources.
                        git(repo, "update-ref", "-d", ref, snapshot["head"])
                elif resource["kind"] == "directory":
                    if Path(resource["path"]).exists():
                        self.inspect_resource(resource)
                        Path(resource["path"]).rmdir()
                else:
                    # Failed inspection never implies absence (daemon/auth failures are blockers).
                    ids = self.docker(resource["kind"], "ls", "--no-trunc", "--quiet", *
                                      (["--all"] if resource["kind"] == "container" else [])).splitlines()
                    if resource["docker_id"] in ids:
                        self.inspect_resource(resource)
                        self.docker(resource["kind"], "rm", resource["docker_id"])
                item.update(status="removed", error=None)
                resource["status"] = "removed"
                atomic_json(self.path / "state.json", self.state)
            except (ValueError, OSError) as error:
                item["error"] = str(error)
                atomic_json(self.path / "state.json", self.state)
        return self.cleanup_status()

    def cleanup_status(self):
        self.only("orchestrator")
        plan = self.state.get("cleanup") or {"items": []}
        removed = [i for i, r in self.state["resources"].items() if r["status"] == "removed"]
        blocked = [dict(i) for i in plan["items"] if i["status"] != "removed"]
        for resource_id in removed[:]:
            r = self.state["resources"][resource_id]
            try:
                if r["kind"] in ("worktree", "directory"):
                    require(not os.path.lexists(r["path"]), "Removed path reappeared; preserve new contents")
                    if r["kind"] == "worktree":
                        ref = "refs/heads/" + r["branch"]
                        check = subprocess.run(["git", "-C", self.state["repo"], "show-ref", "--verify", "--quiet", ref],
                                               capture_output=True)
                        require(check.returncode == 1, "Removed branch reappeared or cannot be checked")
                else:
                    ids = self.docker(r["kind"], "ls", "--no-trunc", "--quiet", *
                                      (["--all"] if r["kind"] == "container" else [])).splitlines()
                    require(r["docker_id"] not in ids, "Removed Docker resource still present")
            except (ValueError, OSError) as error:
                removed.remove(resource_id)
                blocked.append(dict(resource_id=resource_id, status="verification_blocked", error=str(error)))
        retained = [i for i, r in self.state["resources"].items() if r["status"] != "removed" and i not in [b["resource_id"] for b in blocked]]
        if self.state["merge"] and not blocked and all(r["status"] == "removed" for r in self.state["resources"].values()):
            self.state["lifecycle"] = "closed"
        elif self.state["lifecycle"] == "closed":
            self.state["lifecycle"] = "cleanup_pending"
        return dict(lifecycle=self.state["lifecycle"], removed=removed, retained=retained, blocked=blocked,
                    resources=self.state["resources"],
                    recovery_refs=["refs/feature-workflow/" + self.state["feature_id"] + "/" + i
                                   for i in removed if self.state["resources"][i]["kind"] == "worktree"],
                    preserved=["original checkout", "ticket/specs/reports/decisions/checkpoints/state", "recovery refs"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["init", "add-task", "start-task", "submit", "review", "return-task",
                        "integrate", "recover", "revise", "gate", "pr-ready", "record-pr", "register-resource",
                        "cleanup-plan", "cleanup-apply", "cleanup-status"])
    parser.add_argument("--request", required=True, help="UTF-8 JSON object of operation arguments")
    parser.add_argument("--workspace", help="Absolute external feature workspace (except init)")
    parser.add_argument("--actor", default="", help="Unique session/agent identity")
    parser.add_argument("--role", default="", help="planner or orchestrator; role is cooperative, not authentication")
    args = parser.parse_args()
    try:
        request = json.loads(Path(args.request).read_text(encoding="utf-8-sig"))
        if args.operation == "init":
            require(args.role == "planner", "Initialization requires planner")
            require(args.actor, "Actor identity required")
            result = initialize(**request)
        else:
            require(args.workspace and Path(args.workspace).is_absolute(), "Absolute workspace required")
            with Workspace(args.workspace, args.actor, args.role).transaction() as workspace:
                result = getattr(workspace, args.operation.replace("-", "_"))(**request)
        print(json.dumps(result if result is not None else {"ok": True}, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
