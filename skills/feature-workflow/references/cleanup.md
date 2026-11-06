# Cleanup protocol

## Inventory and authority

State schema 2 stores the resource manifest in `state.json.resources`. Keep feature evidence outside temporary worktrees. Before creation, checkpoint intended paths/branches/owners; immediately record actual identities, including failed or interrupted creation. Built-in worktree creation records a creating entry before Git mutation. Inspect initialization checkpoints if creation interrupts before state exists. Workers cannot edit canonical state: report creation intent/results to Orchestrator and require registration acknowledgment. Register review worktrees with purpose review and the task_id/source commit they inspected. A failed registration is unfinished handoff work.

Use `register-resource` for additional worktrees, temporary directories, containers and networks. Exact full Docker IDs and labels `feature-workflow.feature` and `feature-workflow.owner` are required; names alone do not establish ownership. Shared resources stay retained. No global scanning, pruning, force removal or recursive directory deletion. Empty temporary directories can be removed; unknown files block removal and require inspection and separate disposition. The helper never deletes their contents. Original checkout, application processes, ticket, specs, reports, decisions, checkpoints, state and recovery refs remain preserved.

`cleanup-plan` takes resource_ids and stores an exact snapshot plus inventory_sha256. Present it before requesting explicit human approval for this feature and digest. `cleanup-apply` takes that approval, rechecks current paths, ownership, clean state including ignored files, branches and commits, then journals each item before mutation. Scope changes require a new plan and approval after resolving the current plan. Approval of a feature or publication alone never authorizes deletion.

## Squash integration and incremental release

Task/review worktrees become eligible after task completion, exact source HEAD and integration trailers verify against a commit still reachable from integrated_head. Preserve independent reports before planning. Task source ancestry is insufficient for squash integration. Before removing a worktree/branch, preserve its exact HEAD under `refs/feature-workflow/<feature>/<resource>`. These durable recovery refs deliberately remain after cleanup. Git worktree removal uses no force; branch deletion compares the exact expected commit and refuses a branch checked out elsewhere. Report recovery ref names for recovery through Git history.

## Publication and merge

`record-pr` records inspected provider URL/head/base/evidence after current gates pass. It performs no network calls. To record merge, first inspect the provider's merged status, matching PR identity/head/base and merge commit, fetch that commit/base through authorized normal Git operations, then supply merge_commit and the inspected service evidence. The helper checks base reachability and source ancestry or identical published/merged trees for squash/rebase. Divergent squash trees require investigation, not fabricated approval or bypassing checks. The evidence field is a cooperative assertion, not provider authentication.

Only verified merge permits feature worktree/branch deletion. Published, merged, cleanup_pending and closed are separate lifecycle states. Incremental task cleanup leaves active/published unchanged. After merge, execution enters cleanup_pending; closed requires all registered resources removed. Retained resources must be reported and leave closeout pending. Publication never implies cleanup is complete.

## Resume and closeout

Run cleanup-apply again with the same approved digest after interruption. Removed items are skipped. For a removing worktree whose path is absent, verify the durable preservation ref and compare-and-delete only the recorded branch HEAD. Branch movement, dirty/ignored files, linked paths (including Windows junctions), ownership changes or Docker daemon errors block the item. Containers must be stopped; networks must have no attached containers. Docker retry proves absence through successful exact-ID listing; failed inspection never proves absence. Preserve a stale lock until objective owner/session evidence permits deliberate takeover.

`cleanup-status` reports removed, retained, blocked and always-preserved evidence; inspect blocked entries even when the CLI exits successfully. Resolve unknown or changed resources explicitly; never force through a failed preflight. Run status after execution and include exact IDs/paths/branches, recovery refs and reasons in the closeout report. Use Git history for completed feature documentation; keep only reusable development conventions in repository instructions.
