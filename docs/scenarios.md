# Representative workflow scenarios

The automated scenarios in [test_workflow.py](../tests/test_workflow.py) create disposable local Git repositories and external directories with spaces. They execute the shared helper, including actual commits, worktrees, squash integration, and checkpoint recovery. They test cooperative protocol enforcement, not an agent security boundary or a live hosting provider.

| Scenario | Evidence and prohibited action |
| --- | --- |
| Repository initialization | Committed AGENTS.md/GLOSSARY.md are required; existing and nested workspace targets and absent approval are rejected. Dirty staged/unstaged/untracked original checkout remains byte-for-byte and index-equivalent. |
| Planning/decomposition | Stable scoped task records with acceptance IDs and commands; missing/cyclic dependencies and implementer dispatch authority are rejected. |
| Parallel implementation | Two independent branches/worktrees start from the same integrated baseline; both outputs survive serialized squash integration. |
| Independent review | Author self-review, stale commit/spec reports, and post-review edits are rejected. A failed review returns work for repair; a changed submission can be explicitly returned, repaired, resubmitted and reviewed before integration. Completed history cannot be reopened. |
| Squash integration | Exactly one feature commit per task with serial parent chain; an explicit description survives as the subject/body with authoritative feature/task/source/spec trailers. Multi-commit task integration uses the supplied whole-task description. Missing, invalid and obvious reference-only messages fail before mutation, as do unreviewed and duplicate integrations. |
| Requirement changes | Approved consolidated spec revision advances, original ticket and earlier spec remain intact, affected task review is invalidated; unapproved revisions fail. |
| Agent interruption/recovery | Simulated interruption after Git commit but before state result is recovered from parent/tree/trailers/test evidence without duplicate commits, for both new descriptive messages and historical generic subjects. Failed checks leave blocking checkpoints. Live locks are preserved. |
| Feature validation and pre-PR gate | Both current independent reports are mandatory; implementer certification, missing quality gate, and reports invalidated by new commits fail. Unaccounted clean feature commits block dispatch and certification until Git evidence is reconciled. Readiness permits draft only. |
| Cleanup | Inventory digest approval, clean/ignored-file checks, source/tree/check integration evidence, recovery refs, interrupted/repeated removal, merge-gated feature closeout and shared Docker protection. Docker service responses are mocked. |
| Manual library update | Incompatible schema fails safely before resuming operations. Package/install compatibility and existing-destination cases are exercised by [test_library.py](../tests/test_library.py). |

These role-level scenarios also require manual agent evaluation before relying on the library for a production feature:

| Request | Expected observable outcome |
| --- | --- |
| Initialize an unfamiliar repository that already has owner rules | Initializer investigates commands and vocabulary, proposes narrowly scoped AGENTS.md/GLOSSARY.md edits in an isolated worktree, and preserves the original checkout. |
| Write a ticket for an underspecified search feature | Ticket Writer inspects existing search behavior, asks only unresolved product questions, obtains approval for one comprehensive ticket, and does not decompose it. |
| Change an approved requirement during parallel implementation | Orchestrator records explicit human approval and a new consolidated spec, pauses affected agents, invalidates old evidence, and creates corrective tasks for completed work. |
| Fix a login button that remains disabled after authentication fails | Implementer subject: `Fix login button remaining disabled after a failed sign-in`. If the diff re-enables the button on failure, a useful body explains that users can correct credentials and retry. Orchestrator preserves the concrete fix in its squash `message`; `Implement 01` or `Fix task 01` fails the description standard. |
| Reject integration when a task's reviewed source commit has changed | Subject: `Reject integration when the task changed after review`. A body may explain that the HEAD/clean-tree checks prevent integrating unreviewed changes when those checks are present in the diff. The subject identifies the infrastructure behavior without needing the task ID; `Update workflow` is too vague. |
| Integrate a login-button task with an initial fix and a later repair for retry handling | Independent review covers the complete task diff and source descriptions. Orchestrator describes the combined result, for example `Restore login button retries after failed sign-in`, rather than copying a final repair subject such as `Handle the missing error response`. The helper retains the supplied subject/body and authoritative provenance trailers. A message-only source amend requires fresh exact-HEAD review. |
| Address draft PR feedback | Orchestrator distinguishes product changes from technical fixes, dispatches a scoped corrective task, obtains independent review, serially integrates, reruns both gates, and updates the same draft PR with authorization. |
| Resume after overwriting installed skills with a new release | Explicit Library Update compares manifests, inventories supplied active workspaces, checkpoints, proposes instruction-only compatibility updates, and blocks unknown schemas. No automatic install, background monitor, or implementation code edit occurs. |

The three commit-description scenarios above are manual evaluation prompts and expected outcomes, not evidence of live agent runs or implemented login behavior. Assess whether each subject identifies the real change, optional bodies are truthful and useful, and squash metadata remains intact; the automated message tests verify mechanics rather than meaning.

No live issue/PR was published and no installed user skills were overwritten by these tests. Windows PowerShell executes the helpers through Python; Linux Bash command examples receive static review when Bash is unavailable. Report actual execution results with each change; retain completed feature documentation in Git history.
