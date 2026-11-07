---
name: ticket-writer
description: Optionally investigate and interview to prepare one comprehensive human-approved feature ticket, without decomposing or implementing it.
---

# Ticket Writer

## Activation and inputs
Use as an optional preparation utility when the user wants one feature ticket or help clarifying scope. Planner can perform its own interview/approval for unstructured input; this skill is not a required entry point. Inputs: requested outcome, accessible repositories and relevant business constraints. Read the [shared contract](../feature-workflow/references/contracts.md) and [repository intelligence operations](../feature-workflow/references/operations.md). No mode switch is required; use an available question tool or ordinary conversation.

## Authority
Investigate technical facts independently. Humans decide product behavior and business tradeoffs. Produce one comprehensive feature ticket; never split it into tasks, plan implementation, edit implementation code, or publish externally without authorization.

## Procedure
1. Inspect applicable instructions, affected components, callers, tests, APIs, configuration and accessible related work. Record source paths and inspected commits. Distinguish projects needing changes from dependent projects needing verification.
2. Maintain a dependency-aware set of unresolved product decisions. Ask only decisions whose prerequisites are known; investigate repository-answerable questions yourself. Offer concrete options where useful. Recompute after each answer and reopen settled decisions only when new evidence contradicts them.
3. Cross-check proposed behavior against existing contracts and consumers. Record verified conflicts, plausible risks, consequences, agreed resolutions and access gaps. Resolve product conflicts with the human; never silently select different requirements.
4. Draft one self-contained ticket: problem/outcome; in-scope behavior and failure cases; stable acceptance IDs; constraints and compatibility; affected repositories/components; dependencies; settled decisions; exclusions; inspection evidence and unavoidable unknowns. Omit task decomposition and coding steps.
5. Present the complete draft and obtain human approval of that exact content. If changes are requested, revise the affected decisions and reconfirm. Preserve the approved ticket/digest/evidence in a private external handoff location, without reserving Planner's not-yet-created canonical workspace. Planner copies those exact approved inputs during initialization. If file creation is outside the requested scope, return the exact approved content and explicit preservation handoff. Initial drafts, questions and interview artifacts remain outside dashboard listings; Ticket Writer never creates canonical state, tasks, worktrees or visibility eligibility.

## Outputs and completion
One comprehensive approved ticket, its approval evidence and technical findings. An unapproved draft remains private and unapproved. A prepared ticket is reusable by Planner without another interview/approval when its exact scope and approval evidence remain valid. Publishing to an issue tracker is a separately authorized operation and must preserve the local original.

## Failure and recovery
If technical evidence is inaccessible, label the gap and continue independent research where possible. Pause only decisions that depend on the gap. If approval is missing, preserve the draft and unresolved decisions; do not infer approval or begin planning. Later approved changes become versioned consolidated specifications rather than edits to the original ticket.
