# Deterministic helper interface

Requires Python 3.10+ and Git. No service credentials, third-party modules, automatic installation, or background process. CLI role/actor fields are assertions by cooperating agents, not authentication. Never run untrusted test commands; confirm they come from repository instructions and the scoped plan.

Each invocation takes one operation, `--request` pointing to a UTF-8 JSON object, `--actor` containing the unique agent/session ID, and `--role` containing planner or orchestrator. Operations other than init also require `--workspace` as an absolute path. All operation arguments come from the JSON object; unknown arguments fail. CLI success returns JSON and exit 0; failure returns a message on stderr and exit 1. A failure can leave an intentional checkpoint or reserved destination; inspect before retrying. Never simply delete it and restart.

## Operations and JSON fields

| Operation | Role | Required request fields |
| --- | --- | --- |
| init | planner | repo, workspace (new external absolute path), feature_id, ticket (source path), spec (source path), approved; optional base (committed ref, default HEAD) |
| add-task | planner/orchestrator | task_id, depends_on (IDs already added), scope, acceptance_ids, tests (nonempty argument arrays) |
| start-task | orchestrator | task_id, owner (unique implementer identity) |
| submit | orchestrator | task_id; inspect committed worker result first |
| review | orchestrator | task_id, report (independent reviewer artifact copied without altering verdict) |
| return-task | orchestrator | task_id, reason (repair evidence); clears current review for an unfinished task, preserves reports |
| integrate | orchestrator | task_id |
| recover | orchestrator | no fields; empty object |
| revise | orchestrator | spec (new full consolidated specification path), approved, affected_tasks (all affected unfinished IDs) |
| gate | orchestrator | kind (validation/quality), report |
| pr-ready | orchestrator | no fields; empty object; readiness only, no network call |
| register-resource | orchestrator | resource_id, kind, owner, purpose; path/branch/task_id for worktrees, path for directories, docker_id for containers/networks |
| record-pr | orchestrator | url, head, base, evidence; optional merge_commit after inspecting merged PR service evidence |
| cleanup-plan | orchestrator | resource_ids; stores concrete inventory and inventory_sha256, no approval or deletion |
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

## Integration recovery

The helper stores intent before Git mutation and expected staged tree plus successful checks before committing. A subsequent mutation refuses pending intent. `recover` can reconcile an unchanged clean pre-integration HEAD or one clean commit with matching parent, tree, feature/task/source/spec trailers and passing re-run checks. It cannot abort a conflicted squash or decide whether an unknown commit is legitimate. On those cases inspect Git status/diff/index and checkpoint, preserve diagnostics, then repair only the managed feature worktree under Orchestrator ownership. Never touch the original checkout or blindly repeat a squash. State is cooperative, not tamper-resistant.

Requirement revisions preserve completed history. Create corrective tasks for already integrated work; identify all affected unfinished tasks for revision invalidation. Even unaffected old reviews cannot integrate until refreshed for the latest revision. Agents assess product impacts; the helper does not infer them.

Cleanup execution and retry rules are defined in the [cleanup protocol](cleanup.md). Inspect the returned per-item status: exit 0 may include blocked resources; it does not mean closeout succeeded. The old task_ids cleanup request is intentionally unsupported in schema 2.
