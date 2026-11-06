# Feature workflow contract v2

Library version: 1.1.0. State schema: 2. Skills install as sibling directories, including feature-workflow. Every process skill defines activation, inputs, authority, procedure, outputs/completion, and failure/recovery and reads this contract. Instructions are a cooperative protocol, not a security sandbox.

## Ownership and authority

- Human: product/business intent, approval of initial ticket and each requirements revision, PR approval, explicit cleanup authorization.
- Ticket Writer: investigate and interview, produce one comprehensive ticket; never task decomposition or implementation.
- Planner: verify initialization, create external feature state and feature worktree, decompose approved scope; no integration or task completion.
- Orchestrator: sole writer of canonical state after planning, sole integrator and task completer; serializes mutations. Agents write separate reports, never concurrently edit state.
- Implementer: one task branch/worktree; no canonical state writes, integration, or self-review.
- Reviewer: different agent from author; read-only code review tied to exact commit and spec revision.
- Validator and quality gate: independent reports on integrated feature HEAD and latest approved spec. Neither implements fixes while certifying them.
- Initializer: isolated changes to AGENTS.md/GLOSSARY.md, preserving existing owner rules. Subsequently Orchestrator owns instruction/glossary integration; agents propose changes as scoped diffs.
- Library Update: explicit manual invocation only; instructions/state compatibility only, never implementation code, installs, or monitoring.

## External workspace and artifacts

Choose an absolute feature directory outside every repository worktree (default sibling directory named `<repository>-features/<feature-id>`); ensure Git cannot track it. Never put it in a checked-out tree even if ignored. Use distinct workspace per feature. Preserve original checkout branch, HEAD, status, index, and untracked files; never stash/reset/clean it. Read baseline from a committed ref; disclose that uncommitted changes are excluded.

Artifacts: immutable `ticket.md`; `specs/0001.md` then monotonic consolidated full specifications; `state.json`; append-only `decisions/`; `reports/` with unique generation/task/agent or attempt identifiers; `checkpoints/`; `pr.md`. No private feature data in the skill library. Each approval records human identity/session evidence, date, artifact digest, and approved revision. A proposed change is not approved by silence.

State fields: `schema_version`, `library_version`, `feature_id`, `repo`, `original` (branch/head/status), `feature_branch`, `feature_worktree`, `base_commit`, `integrated_head` (last verified feature commit), `ticket_sha256`, `spec_revision`, `spec_sha256`, `spec_approval`, `tasks`, `gates`, `integration`, `pr`, `cleanup_authorization`, `generation`. Task map entries contain `status`, `depends_on`, `owner`, `branch`, `worktree`, `base_commit`, `head`, `review`, `integration_commit`, `integration_evidence` (source, parent, tree, spec and successful checks). Gates are `validation` and `quality`, each with `passed`, `head`, `spec_revision`, `report`, `agent`. Initialization helper creates the minimal empty fields; Planner fills task ownership/scope and requirements mapping before dispatch.

Task scope additionally records acceptance IDs, file/component ownership, interface contracts, test commands, dependencies, and completion evidence. IDs are stable. A dependency graph must be acyclic, IDs unique, referenced tasks present. Overlapping ownership is serialized or redesigned before dispatch.

## Lifecycle and evidence

Task transitions: pending -> implementing -> review -> reviewed -> complete. Review rejection returns review -> implementing with a new attempt. Blocking/interruption is recorded in checkpoints without claiming completion. Dependencies must be complete before implementation begins. Only Orchestrator marks complete after a verified squash integration commit on the feature branch. Review report contains author and reviewer identities (must differ), exact task HEAD, spec revision, findings with severity and location, test evidence, and verdict. New commits or requirements invalidate review. Requirements changes invalidate both feature gates; assess/reopen affected tasks and reviews explicitly.

Integration is serialized under a workspace lock. Preflight verifies clean managed feature tree, expected branch/HEAD, approved current spec, exact reviewed task HEAD, completed dependencies, and ancestry of task base. Checkpoint intent (task/head/pre-integration HEAD/spec) before Git mutation. Squash merge then commit with feature/task/source-head/spec trailers. Verify actual commit and resulting tree; save completion and evidence atomically. Never mark complete on merge conflict or test failure. Abort only the managed merge, preserve evidence, and return task for repair/review. Do not reset or delete ambiguous commits on retry.

Recovery: read last checkpoint and Git log/tree/status/worktree list; distinguish no mutation, prepared squash, committed-but-state-not-saved, and recorded completion. Reconcile only a uniquely matching commit with matching parent, trailers, tree and validation evidence. Otherwise stop integration for investigation. Never blindly repeat a commit or force-remove locks; confirm owner stopped, record takeover, then remove a stale lock. Retry at most once after an understood transient failure; repeated or ambiguous failure escalates to Orchestrator, technical facts remain agent responsibility.

## Gates, PR, and cleanup

Before draft PR: every task complete, latest spec approved, feature-wide validation and mandatory pre-PR quality gate pass for exact current HEAD/spec; all blocking findings resolved and re-reviewed. Validation maps every acceptance criterion to executable or explicit manual evidence; skipped/unavailable required checks block. Quality audits completeness, maintainability, architecture, duplication, terminology and test quality. Commit/spec changes invalidate both gates. PR publishing requires authorization from the user's feature request or an explicit publishing instruction; draft only, never approve/merge. Check existing PR by repository/head/base before retry; record URL and head. PR feedback is a new scoped task, reviewed/integrated/validated/gated before pushing updates.

Cleanup uses the [cleanup protocol](cleanup.md): a resource manifest recorded at creation, immutable concrete inventory, human approval bound to its digest, durable per-item execution and closeout reports. Feature lifecycle is active -> published -> merged -> cleanup_pending -> closed. Publication does not authorize or complete cleanup. Task/review cleanup can occur incrementally while active/published without changing that lifecycle. Only verified PR merge permits feature worktree/branch removal. Preserve the original checkout, running application, shared resources and durable recovery evidence.

Schema 2 adds `lifecycle`, `merge`, `resources`, and `cleanup`. `resources` is the feature resource manifest, keyed by stable resource ID with kind, exact path/branch or full Docker ID, owner, purpose, task_id and status. `cleanup` stores the inventory, SHA256 and per-item pending/removing/removed status and error. `cleanup_authorization` binds human/session/date to feature_id and inventory_sha256. Merge records inspected service evidence, published head, base and locally verified merge commit. Old schemas require manual reconciliation and explicit resource inventory; never infer ownership from directory names.

## Compatibility

Manual releases include all sibling skills and a manifest with library/schema version and content hashes. During manual update compare old/new manifests, detect missing/mixed resources and schema/authority changes, inventory active workspaces from user-provided locations (no global scanning), checkpoint first, and propose instruction-only changes in isolated worktrees. Unknown major/schema versions block resumption. Never rewrite ticket/history or infer product approval. Preserve backups and rollback instructions; do not resume agents until the single Orchestrator reconciles compatibility.


