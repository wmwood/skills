# Representative workflow scenarios

The workflow scenarios in [test_workflow.py](../tests/test_workflow.py) create disposable local Git repositories and external directories with spaces. They execute the shared helper, including actual commits, worktrees, squash integration, and checkpoint recovery. They test cooperative protocol enforcement, not an agent security boundary or a live hosting provider.

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
| Manual library update | Incompatible schema fails safely before resuming operations. Explicit visibility adoption retains unknown history and supports only its documented rollback window. |
| Structured visibility | [Recording tests](../tests/test_visibility_recording.py) preserve owner/approval boundaries, initial eligibility, blocker/feedback history and actual observation times. |
| Pure projection | [Model tests](../tests/test_snapshot_model.py) distinguish lifecycle/phases/readiness/freshness, obsolete evidence and unknown liveness. Cleanup proof respects resource kinds and successive inventories. |
| Read-only discovery | [Reader](../tests/test_snapshot_reader.py) and [CLI](../tests/test_snapshot_cli.py) checks bound configured discovery, retain healthy sources on failure and verify nonmutation with held locks and cache-free entry points. |
| Dashboard states/failures | The synthetic [fixture catalog](../tests/fixtures/dashboard/catalog.json) and [public acceptance checks](../tests/test_dashboard_acceptance.py) cover initial exclusion, later waits, recorded outcomes and malformed/unsupported/missing/stale/inconsistent data. |
| Distributed consumer | [Library tests](../tests/test_library.py) verify package/install resource hashes, existing-destination refusal and snapshot CLI/callable use without repository-only scripts. Private test configuration/workspaces use external temporary locations. |

These role-level scenarios also require manual agent evaluation before relying on the library for a production feature:

| Request | Expected observable outcome |
| --- | --- |
| Initialize an unfamiliar repository that already has owner rules | Initializer investigates commands and vocabulary, proposes narrowly scoped AGENTS.md/GLOSSARY.md edits in an isolated worktree, and preserves the original checkout. |
| Optionally write a ticket for an underspecified search feature | Ticket Writer inspects existing search behavior, asks only unresolved product questions, obtains approval for one comprehensive ticket, and does not decompose it. |
| Send an unstructured request directly to Planner | Planner investigates/interviews before explicit human scope approval, then produces tasks and initial visibility evidence. Earlier drafts/questions remain outside listings. |
| Give Planner an already approved comprehensive ticket | Planner verifies the exact approval and reuses its scope without a redundant interview/approval; new product contradictions still return to the human. |
| Inspect a feature waiting on later requirements approval | The established feature remains visible with a separate feedback/phase record; proposed requirements do not receive inherited approval. |
| Change an approved requirement during parallel implementation | Orchestrator records explicit human approval and a new consolidated spec, pauses affected agents, invalidates old evidence, and creates corrective tasks for completed work. |
| Address draft PR feedback | Orchestrator distinguishes product changes from technical fixes, dispatches a scoped corrective task, obtains independent review, serially integrates, reruns both gates, and updates the same draft PR with authorization. |
| Resume after overwriting installed skills with a new release | Explicit Library Update compares manifests, inventories supplied active workspaces, checkpoints, proposes instruction-only compatibility updates, and blocks unknown schemas. No automatic install, background monitor, or implementation code edit occurs. |

Tests use disposable resources and do not publish to providers or install into real user skill collections. Record actual Windows PowerShell 5.1 and Linux Bash coverage separately; Git Bash syntax checking is not Linux execution. Report skips and unavailable checks explicitly, with exact-commit evidence outside the repository.
