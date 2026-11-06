---
name: feature-planner
description: Turn an approved feature ticket into dependency-aware tasks and an isolated feature workspace after verifying repository initialization.
---

# Feature Planner

## Activation and inputs
Use to plan implementation of an approved feature. Inputs: approved ticket and approval evidence, repository, explicit committed baseline and available workspace location. Read the [shared contract](../feature-workflow/references/contracts.md) and [shared operations](../feature-workflow/references/operations.md). Requires Git and Python 3.10+ for deterministic helpers; no mode switch is required.

## Authority
Create the feature branch/worktree and initial external state, specification and task plan. Do not implement tasks, integrate branches, mark tasks complete, approve product changes, or modify the original checkout. Planning authorization does not authorize dispatch or publishing.

## Procedure
1. Inspect instructions and Git state. Verify AGENTS.md and GLOSSARY.md exist and describe repository commands, architecture, ownership and terminology; route missing initialization to Repository Initializer before implementation planning. Capture original branch, HEAD, status and index evidence without stashing, cleaning or changing them.
2. Verify human approval applies to the exact ticket. Investigate components, interfaces, tests and technical dependencies yourself. Escalate only a genuine product contradiction; do not substitute a different requirement.
3. Resolve an absolute external workspace outside all checked-out trees. Check absence of target branch/path; choose unique `codex/<feature>` naming. Create the isolated feature worktree from the explicit committed baseline using the utility helper's supported operations. Disclose that original uncommitted work is excluded. Never reuse existing paths on a fresh creation attempt.
4. Preserve immutable `ticket.md`, create full `specs/0001.md` with stable acceptance IDs and matching approval evidence, and initialize contract-compliant `state.json`. Read the [helper request interface](../feature-workflow/references/cli.md) and CLI help before using it; record partial creation in a checkpoint rather than overwriting it.
5. Decompose into independently implementable tasks. Each task records acceptance IDs, scope and excluded work, file/component ownership, interface contracts, dependencies, test commands as argument arrays, expected deliverables and baseline requirements. Validate unique IDs, present dependencies and an acyclic graph. Serialize overlapping ownership or redesign boundaries; do not dispatch competing edits. Task branches use `codex/<feature>-task-<id>` to avoid a Git ref prefix collision with the feature branch.
6. Cover every acceptance criterion with tasks and a feature-wide validation strategy. Identify review, integration, quality gate and PR prerequisites. Initialize tasks as pending and leave runtime review/integration evidence unset. Handoff the plan and single-writer ownership to Orchestrator only when execution is authorized.

## Outputs and completion
An isolated feature branch/worktree, preserved ticket, approved initial consolidated specification, initialized external state, dependency-safe task plan, acceptance coverage and dispatch handoff. Report original-checkout preservation and unresolved blockers. No task is complete merely because planning finished.

## Failure and recovery
Reject missing approval, unsafe paths, pre-existing creation targets, cycles or unexplained ownership collisions. Preserve partial artifacts and inspect actual worktrees/branches/state before retry. Never delete or reset the original checkout. If initialization or execution authorization is missing, return the concrete prerequisite without implementing.

## Resource handoff
Transfer the schema 2 resource manifest and any creation checkpoints to Orchestrator with exact feature worktree path, branch, owner and original checkout identity. Reconcile interrupted creation before dispatch. Additional resources must be registered as created under the [cleanup protocol](../feature-workflow/references/cleanup.md); planning and publication do not authorize deletion.
