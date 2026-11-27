# Deterministic helper interface

Requires Python 3.10+ and Git. No service credentials, third-party modules, automatic installation, or background process. CLI role/actor fields are assertions by cooperating agents, not authentication. Never run untrusted test commands; confirm they come from repository instructions and the scoped plan.

Each invocation takes one operation, `--request` pointing to a UTF-8 JSON object, `--actor` containing the unique agent/session ID, and `--role` containing planner or orchestrator. Operations other than init also require `--workspace` as an absolute path. All operation arguments come from the JSON object; unknown arguments fail. CLI success returns JSON and exit 0; failure returns a message on stderr and exit 1. A failure can leave an intentional checkpoint or reserved destination; inspect before retrying. Never simply delete it and restart.

## Initialize

The helper derives and validates the new path using the primary checkout and the [workspace contract](contracts.md#external-workspace-and-artifacts). Omit `--workspace` for init. A legacy `workspace` JSON field must match the derived path or init fails before creating files or refs. If linked-checkout metadata cannot establish the primary checkout path, pass the primary checkout directly as `repo` and supply a committed `base` if needed. Request access to the required path when the session cannot write there. Report an access denial with the derived path and stop.

## Operations and JSON fields

| Operation | Role | Required request fields |
| --- | --- | --- |
| init | planner | repo (checkout path), feature_id, ticket (source path), spec (source path), approved. Optional base (committed ref, default HEAD in the supplied checkout). An older request may include workspace as an exact assertion of the derived absolute path. |
| add-task | planner/orchestrator | task_id, depends_on (IDs already added), scope, acceptance_ids, tests (nonempty argument arrays) |
| start-task | orchestrator | task_id, owner (unique implementer identity) |
| submit | orchestrator | task_id; inspect committed worker result first |
| review | orchestrator | task_id, report (independent reviewer report object, copied without altering verdict) |
| return-task | orchestrator | task_id, reason (repair evidence); clears current review for an unfinished task, preserves reports |
| integrate | orchestrator | task_id, message (descriptive subject and optional explanatory body) |
| recover | orchestrator | no fields; empty object |
| revise | orchestrator | spec (new full consolidated specification path), approved, affected_tasks (all affected unfinished IDs) |
| gate | orchestrator | kind (validation/quality), report |
| pr-ready | orchestrator | no fields; empty object; readiness only, no network call |
| register-resource | orchestrator | resource_id, kind, owner, purpose. Supply path/branch/task_id for worktrees, path for directories, or docker_id for containers/networks. Task and review worktrees must be direct children of the workspace's tasks and reviews directories, respectively. Set `track_attempt: true` for review worktrees that should retain attempt evidence. Validation and quality worktrees track attempts automatically. |
| record-pr | orchestrator | url, head, base, evidence; optional merge_commit after inspecting merged PR service evidence |
| finish-worktree-attempt | orchestrator | resource_id, report (full attempt report object) |
| record-build-output | orchestrator | resource_id, directories (worktree-relative output roots), command (trusted synchronous argument array) |
| cleanup-plan | orchestrator | resource_ids. Optional replaces_inventory_sha256 identifies the exact unfinished inventory to archive and replace. Returns the new inventory and digest for approval. |
| cleanup-apply | orchestrator | authorized: human, evidence, date, feature_id, inventory_sha256 |
| cleanup-status | orchestrator | no fields; removed, retained, blocked, preserved evidence and lifecycle |

Approval object: `human`, `evidence` (session/message reference), `date` (ISO date). The helper binds approval to the copied spec revision and SHA256. The agent must actually obtain and inspect human approval; fabricated fields do not authorize anything. Initial approval covers ticket and specification. No decision questions about inspectable repository facts.

Review report: `agent`, `head`, `spec_revision`, `tests` (evidence), `findings` (array), `verdict` (pass/fail). Preserve severity, location and rationale in findings; a passing verdict requires all blocking findings resolved. The reviewer must be a different agent from the author. Changing HEAD or spec invalidates review. Reports are stored under generation-based unique names, not overwritten.

Gate report: `agent`, `head`, `spec_revision`, `passed` (JSON boolean), `evidence` (acceptance/check mapping plus commands/results/report paths). Gate agents cannot be task authors. Passing tests alone do not establish completeness, architecture quality or requirements approval.

Task test example (JSON):

```json
{"task_id":"api","depends_on":[],"scope":["src/api"],"acceptance_ids":["AC-1"],"tests":[["python","-m","unittest","discover"]]}
```

Use repository-specific commands, not this sample by default. Helpers run tests in the feature worktree after preparing the squash and before committing. They reject nonzero results and changed tracked/index/untracked content. Ignored build output is allowed. Checks have a ten-minute timeout each; use a narrower scoped command or manual checkpoint procedure for longer suites. Output is local checkpoint evidence and must be reviewed before sharing for secrets/private data.

## Build output and worktree attempts

Use the actual completed report object for `finish-worktree-attempt`. Include `resource_id`, `agent`, `head`, and `spec_revision`. A review attempt also uses the review report fields and `task_id`. A gate attempt uses `kind`, `passed`, and `evidence`. Record a tracked review attempt before its canonical `review`, or a gate attempt before submitting a current `gate`. A failed or superseded attempt can support cleanup independently of canonical review and gate decisions.

`record-build-output` runs the supplied command in the registered worktree. Use only a trusted build that finishes writing before exit. Supply distinct non-overlapping relative directories and a nonempty argument array. Commands time out after ten minutes. The helper snapshots each declared directory before and after success and preserves the report and digest. Existing unverified data stays protected. See the [cleanup protocol](cleanup.md) for approval, compatibility, and retry behavior.

## Integration commit messages

New integration requests require `message`; the helper does not generate a task-reference subject or copy only the worker's latest commit. Orchestrator writes a description of the entire independently reviewed task, including repairs, based on the actual diff. For example:

```json
{"task_id":"login-retry","message":"Fix login button remaining disabled after a failed sign-in\n\nRe-enable the button after authentication fails so users can correct their credentials and retry."}
```

Use only claims supported by that task's reviewed change. A single subject is sufficient when additional context adds little; separate an optional body from the subject with a blank line. The helper accepts natural descriptive language without requiring Conventional Commits or a fixed subject length. It rejects missing, blank or non-string input, NUL characters, and obvious reference-only subjects such as `Implement <task-id>`, `Integrate 01`, or `Fix task 01`. This catches placeholders, not semantic accuracy: Orchestrator and independent review must assess whether the description reflects the actual change.

The helper appends authoritative `Feature`, `Task`, `Source-Head`, and `Spec-Revision` trailers. Do not include those fields in the supplied message; reserved field lines (case-insensitive, with a colon or equals sign) are rejected to avoid conflicting evidence. Validation precedes any squash mutation or pending integration checkpoint.

Compatibility: callers that previously sent only `task_id` must add `message` before starting a new integration. No state-schema migration is needed. Existing schema-2 workspaces and interrupted integrations remain recoverable using their original parent/tree/trailer evidence, including historical generic subjects; never amend reviewed source commits or rewrite historical integrations to adopt this standard.

## Integration recovery

The helper stores intent before Git mutation and expected staged tree plus successful checks before committing. A subsequent mutation refuses pending intent. `recover` can reconcile an unchanged clean pre-integration HEAD or one clean commit with matching parent, tree, feature/task/source/spec trailers and passing re-run checks. It cannot abort a conflicted squash or decide whether an unknown commit is legitimate. On those cases inspect Git status/diff/index and checkpoint, preserve diagnostics, then repair only the managed feature worktree under Orchestrator ownership. Never touch the original checkout or blindly repeat a squash. State is cooperative, not tamper-resistant.

Requirement revisions preserve completed history. Create corrective tasks for already integrated work; identify all affected unfinished tasks for revision invalidation. Even unaffected old reviews cannot integrate until refreshed for the latest revision. Agents assess product impacts; the helper does not infer them.

Cleanup execution and retry rules are defined in the [cleanup protocol](cleanup.md). Inspect the returned per-item status: exit 0 may include blocked resources; it does not mean closeout succeeded. The old task_ids cleanup request is intentionally unsupported in schema 2.
