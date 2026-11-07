---
name: feature-planner
description: Interview an unstructured feature request or reuse an approved ticket, then create dependency-aware tasks and an isolated feature workspace after scope approval and repository initialization.
---

# Feature Planner

## Activation and inputs
Use to prepare a feature for implementation. Inputs: an unstructured request, draft or prepared ticket; any existing approval evidence; repository; explicit committed baseline; and available external workspace location. Ticket Writer is optional. Read the [shared contract](../feature-workflow/references/contracts.md) and [shared operations](../feature-workflow/references/operations.md). Requires Git and Python 3.10+ for deterministic helpers; no mode switch is required.

## Authority
Investigate and interview to define scope, obtain human approval, then create the feature branch/worktree, initial external state, specification and task plan. Humans approve product behavior. A request or invocation of Planner is not scope approval. Do not implement tasks, integrate branches, mark tasks complete, approve product changes, or modify the original checkout. Planning authorization does not authorize dispatch or PR publishing.

## Procedure
1. Inspect instructions and Git state. Verify AGENTS.md and GLOSSARY.md exist and describe repository commands, architecture, ownership and terminology; route missing initialization to Repository Initializer before implementation planning. Capture original branch, HEAD, status and index evidence without stashing, cleaning or changing them.
2. Resolve scope before decomposition. For an unstructured, incomplete or unapproved request, inspect repository-answerable facts, interview the owner only on unresolved product decisions, and present one comprehensive scope draft with stable acceptance IDs, constraints and failure cases. Keep drafts, questions and investigation evidence outside repository worktrees. Obtain explicit human approval of the exact scope and record its artifact digest/date/session evidence. Reuse a valid prepared approved ticket without repeating interview or approval; changed or contradictory scope requires approval of the affected consolidated scope before planning. Unanswered questions never imply approval. Do not produce task tickets or initialize canonical feature state/worktrees until scope approval is established.
3. Resolve an absolute external feature workspace outside all checked-out trees. Check absence of target branch/path; choose unique `codex/<feature>` naming. Prepare the isolated feature worktree destination and explicit committed baseline; the next step creates it once through init. Disclose that original uncommitted work is excluded. Never reuse existing paths on a fresh creation attempt; keep any earlier private scope-draft/handoff location separate from the new canonical workspace.
4. Prepare approved ticket/specification inputs in the separate external handoff location. Reuse the exact approved ticket content for the initial full specification unless a different full specification already has matching explicit approval evidence. Read the [helper request interface](../feature-workflow/references/cli.md) and CLI help, then invoke init once to preserve immutable `ticket.md` and `specs/0001.md`, initialize `state.json` and create the feature worktree. Do not precreate its reserved workspace/path/branch. Record partial creation in a checkpoint rather than overwriting it.
5. Decompose the approved scope into independently implementable task tickets and canonical task entries. Each records acceptance IDs, scope and excluded work, file/component ownership, interface contracts, dependencies, test commands as argument arrays, expected deliverables and baseline requirements. Validate unique IDs, present dependencies and an acyclic graph. Serialize overlapping ownership or redesign boundaries; do not dispatch competing edits. Task branches use `codex/<feature>-task-<id>` to avoid a Git ref prefix collision.
6. Cover every acceptance criterion with tasks and a feature-wide validation strategy; identify review, integration, quality gate and PR prerequisites. Keep tasks pending and runtime ownership/review/integration evidence unset.
7. Prepare the plan and resource/context handoff. Transfer sole canonical ownership to Orchestrator only when execution is authorized. Planner stops canonical writes after handoff; planning does not authorize implementation dispatch.

## Outputs and completion
An approved exact-scope ticket and approval evidence; isolated feature branch/worktree; approved initial consolidated specification; initialized external state; complete dependency-safe task tickets/acceptance coverage; and a prepared dispatch handoff. Report original-checkout preservation and unresolved blockers. Planning completion is neither task completion nor execution/PR authorization.

## Failure and recovery
Missing scope approval keeps the draft and interview private and prevents decomposition/initialization. Reject unsafe paths, pre-existing creation targets, cycles or unexplained ownership collisions. Preserve partial artifacts and inspect actual worktrees/branches/state before retry; never delete or reset the original checkout. If execution authorization is missing, return the prepared plan without dispatch.

## Resource handoff
Transfer the schema 2 resource manifest and creation checkpoints with exact feature worktree path, branch, owner and original checkout identity. Reconcile interrupted creation before dispatch. Register additional resources under the [cleanup protocol](../feature-workflow/references/cleanup.md); planning and publication do not authorize deletion.
