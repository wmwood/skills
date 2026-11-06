# Representative workflow scenarios

The automated scenarios in [test_workflow.py](../tests/test_workflow.py) create disposable local Git repositories and external directories with spaces. They execute the shared helper, including actual commits, worktrees, squash integration, and checkpoint recovery. They test cooperative protocol enforcement, not an agent security boundary or a live hosting provider.

| Scenario | Evidence and prohibited action |
| --- | --- |
| Repository initialization | Committed AGENTS.md/GLOSSARY.md are required; existing and nested workspace targets and absent approval are rejected. Dirty staged/unstaged/untracked original checkout remains byte-for-byte and index-equivalent. |
| Planning/decomposition | Stable scoped task records with acceptance IDs and commands; missing/cyclic dependencies and implementer dispatch authority are rejected. |
| Parallel implementation | Two independent branches/worktrees start from the same integrated baseline; both outputs survive serialized squash integration. |
| Independent review | Author self-review, stale commit/spec reports, and post-review edits are rejected. A failed review returns work for repair; a changed submission can be explicitly returned, repaired, resubmitted and reviewed before integration. Completed history cannot be reopened. |
| Squash integration | Exactly one feature commit per task with serial parent chain; unreviewed and duplicate integrations fail. |
| Requirement changes | Approved consolidated spec revision advances, original ticket and earlier spec remain intact, affected task review is invalidated; unapproved revisions fail. |
| Agent interruption/recovery | Simulated interruption after Git commit but before state result is recovered from parent/tree/trailers/test evidence without duplicate commits. Failed checks leave blocking checkpoints. Live locks are preserved. |
| Feature validation and pre-PR gate | Both current independent reports are mandatory; implementer certification, missing quality gate, and reports invalidated by new commits fail. Unaccounted clean feature commits block dispatch and certification until Git evidence is reconciled. Readiness permits draft only. |
| Cleanup | Inventory digest approval, clean/ignored-file checks, source/tree/check integration evidence, recovery refs, interrupted/repeated removal, merge-gated feature closeout and shared Docker protection. Docker service responses are mocked. |
| Manual library update | Incompatible schema fails safely before resuming operations. Package/install compatibility and existing-destination cases are exercised by [test_library.py](../tests/test_library.py). |

These role-level scenarios also require manual agent evaluation before relying on the library for a production feature:

| Request | Expected observable outcome |
| --- | --- |
| Initialize an unfamiliar repository that already has owner rules | Initializer investigates commands and vocabulary, proposes narrowly scoped AGENTS.md/GLOSSARY.md edits in an isolated worktree, and preserves the original checkout. |
| Write a ticket for an underspecified search feature | Ticket Writer inspects existing search behavior, asks only unresolved product questions, obtains approval for one comprehensive ticket, and does not decompose it. |
| Change an approved requirement during parallel implementation | Orchestrator records explicit human approval and a new consolidated spec, pauses affected agents, invalidates old evidence, and creates corrective tasks for completed work. |
| Address draft PR feedback | Orchestrator distinguishes product changes from technical fixes, dispatches a scoped corrective task, obtains independent review, serially integrates, reruns both gates, and updates the same draft PR with authorization. |
| Resume after overwriting installed skills with a new release | Explicit Library Update compares manifests, inventories supplied active workspaces, checkpoints, proposes instruction-only compatibility updates, and blocks unknown schemas. No automatic install, background monitor, or implementation code edit occurs. |

No live issue/PR was published and no installed user skills were overwritten by these tests. Windows PowerShell executes the helpers through Python; Linux Bash command examples receive static review when Bash is unavailable. Report actual execution results with each change; retain completed feature documentation in Git history.
