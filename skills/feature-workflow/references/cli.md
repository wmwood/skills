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

## Structured visibility recording

The read-only snapshot interface is defined in [snapshot.md](snapshot.md). These operations are **writer operations**, not status reads. They use the existing exclusive transaction, approval/digest checks and generation update. Workers submit reports to the canonical owner; they cannot invoke these mutations. Nothing in a feedback answer, activity report or control record grants product, publishing or cleanup authority.

New `init` requests may include `workspace_id`, a stable ID using the snapshot configuration ID grammar. This creates version 1.0.0 metadata with null eligibility; it does not publish the feature. Omitting the field preserves legacy schema 2 behavior. Keep this ID when relocating a workspace.

| Operation | Writer | Request fields |
| --- | --- | --- |
| adopt-visibility | Planner before handoff / Orchestrator | workspace_id, quiescent: true, evidence |
| rollback-visibility | Current canonical owner | backup, backup_sha256, current_sha256, quiescent: true, evidence |
| publish-visibility | Planner before handoff / Orchestrator | Optional task_ids; default all produced tasks |
| record-control | Planner before handoff / Orchestrator | execution_authorized (Boolean), evidence |
| record-phase | Current canonical owner | operation_id, phase, status, reported_at, artifact |
| record-blocker | Current canonical owner | blocker_id, reason, resolution_condition, blocks; optional responsible, artifacts, status (open by default) |
| record-feedback | Current canonical owner | feedback_id, question, artifact (nullable), blocks, blocking (Boolean); optional respondent, status, answer, disposition |
| record-assignment | Current canonical owner | assignment_id, agent_id, role; optional task_id, last_activity, chats |
| record-activity | Current canonical owner | activity |

Artifacts and source record shapes follow the snapshot reference. File evidence must exist inside the workspace, without linked/escaping path components; a supplied digest must match. URI evidence is preserved without fetching it. Evidence references remain cooperative assertions, not authentication. A source artifact_id is optional and must use the snapshot/configuration stable-ID grammar; the snapshot contract defines stable output identity and honest unavailable identity.

publish-visibility verifies a nonempty well-formed task DAG and the current approval binding, then preserves the produced task IDs, exact approval/revision/digest and actual recording time as immutable initial eligibility. It does not approve scope. The marker is retained through later specification revisions; approval of a proposed revision still requires the normal human process. Earlier interviews/drafts/empty initialization remain excluded. Legacy approved planned work remains readable without adopting metadata or rerunning Planner.

record-control reports the invoking writer's own role. Planner can record only false execution authority. Orchestrator may report the actual execution authorization with its evidence. Once control records Orchestrator ownership, subsequent Planner transactions are rejected, including existing add-task. This supplements, rather than replaces, the existing cooperative role boundary.

Phase values are investigating/awaiting_specification_approval/integrating/validating; statuses are active/finished. Use a new operation ID after finishing an operation. An active phase is recorded workflow activity, not proof a process is live. Reported event timestamps require RFC 3339 timezone information; they must come from real observations, not filesystem times. Approval date remains an ISO calendar date (YYYY-MM-DD). Timestamp-form or invalid calendar approval dates are unsupported proof for new visibility publication/adoption, and are preserved unchanged rather than truncated or repaired.

Blocker targets are feature, task:<id>, operation:<id>, or phase:<phase>. Resolution requires supporting artifact evidence; reopening retains prior content/history. New feedback starts open. Answered requires an answer; resolved/withdrawn requires a disposition. Each response records text, by, recorded_at and artifacts. Reopening preserves prior answers/dispositions in history. Answers do not change specification approval. Assignment records require actual known agent/session identity and role; missing chat URI stays null. Activity execution may report running/stopped only with explicit observation time and artifact evidence; task status or owner alone never supplies that observation.

### Explicit adoption and rollback

Keeping an existing workspace legacy and read-only is supported. No ordinary operation automatically adds visibility metadata. To adopt, coordinate quiescence with the canonical owner, inspect existing approval/task/artifact evidence, and supply an actual instruction/session artifact as evidence. Do not remove another writer's lock. adopt-visibility creates a unique durable backups/visibility-<unique-id>.json containing the previous complete state and returns its path/digest. The actual adoption recording time is not a historical creation, transition or approval time. For already planned legacy data with verified current approval and a valid nonempty task DAG, adoption binds those existing facts as initial visibility evidence at the actual adoption recording time, so the feature does not disappear. Invalid legacy proof remains unverified/unpublished. Missing phases/blockers/feedback/assignments/activity collections remain omitted (not_recorded), rather than synthesizing known-empty history. Each typed report starts recording its own kind from then onward; it does not claim a complete recovered history.

Rollback is narrowly limited to this adoption: provide its exact backup path/digest, the current state.json SHA256, quiescence acknowledgment and evidence. It is allowed only immediately after adoption with no intervening canonical transaction and unchanged non-visibility content. It removes the added extension while preserving the generation sequence, backup and durable rollback report. It never restores old task state, rewrites tickets/specs or overwrites newer work. After any subsequent transaction, reconcile through Library Update instead of forcing rollback. Unsupported visibility versions block writer resumption and require explicit compatibility review; readers never invoke adoption or rollback.

All record operations preserve distinct immutable report files in reports/ in addition to canonical metadata/history. Evidence files and backups are durable private artifacts outside repositories and are not cleanup targets.
