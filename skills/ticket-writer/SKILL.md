---
name: ticket-writer
description: Interview a user to turn an underspecified feature or change into confirmed, ticket-ready bullet points for a coworker. Reuses feature-planner's design interview in Plan mode and stops before implementation planning.
---

# Ticket Writer

Build shared understanding of work another person will implement. The deliverable is a self-contained bullet list the user can paste into a ticket.

## Reuse the Feature Planner Interview

Read [feature-planner](../feature-planner/SKILL.md) before starting. If it is unavailable, report the missing dependency and stop.

Use its **Require Plan Mode**, **Model the Design Tree**, **Interview in Dependency-Aware Rounds**, and **Separate Facts from Decisions** sections as the interview workflow. Apply its Plan mode check to this skill: outside Plan mode, ask the user to switch to Plan mode and invoke `$ticket-writer` again.

This skill replaces the source's **Confirm Shared Understanding** and **Propose the Plan** sections with the completion procedure below. The source's plan-generation endpoint does not apply here.

Resolve the decisions needed for a coworker to understand the intended outcome and verify completion. Leave implementation choices to the coworker unless the user requires a particular approach or an existing system imposes a verified constraint. If repository or system facts are inaccessible, label the relevant unknowns instead of inventing details.

## Identify Affected Projects and Cross-Check Conflicts

Before confirming the ticket, inspect the available project structure, references, callers, shared contracts, configuration, tests, and documentation to identify the anticipated projects or repositories to touch. For each, name the likely affected component and explain why a change is expected. Distinguish projects expected to need edits from dependent projects that may only need compatibility verification. Ground the list in evidence and label uncertain entries as anticipated rather than confirmed.

Cross-check the proposed behavior against existing behavior and requirements, shared APIs and schemas, data flows, configuration, and downstream consumers. Where accessible and relevant, inspect current local changes and known related tickets or branches for overlapping or contradictory work. Focus on conflicts plausibly caused by this change; avoid a generic risk checklist.

For each potential conflict, record the affected project or consumer, supporting reference, likely consequence, and a required decision, compatibility constraint, coordination need, or observable verification criterion. Separate verified contradictions from plausible risks. Feed conflicts that require user intent back into the design tree before confirmation; do not silently choose a resolution. Recheck affected relationships when an answer materially changes the scope.

Report what was checked and any material gaps in access or evidence. If no conflict is found, say none was identified within the inspected scope; do not imply that uninspected projects or concurrent work were checked. Keep this investigation at the level needed for a reliable ticket handoff, without turning it into an implementation plan.

## Confirm the Ticket Content

When every meaningful branch has been resolved, intentionally rejected, or marked out of scope and the frontier is empty, present draft ticket bullets covering the applicable items:

- A concise title and the problem or desired outcome.
- In-scope behavior, including relevant edge cases and failure behavior.
- Observable, testable acceptance criteria.
- Settled decisions, constraints, and required compatibility.
- Dependencies or prerequisites and relevant verified context or references.
- Anticipated projects or repositories to touch, their affected components, and the reason each is included; distinguish dependent projects requiring verification only.
- The conflict cross-check result, including concrete potential impacts, agreed resolutions or coordination needs, relevant verification criteria, and material inspection gaps.
- Rejected approaches and explicit exclusions that affect the handoff.
- Unavoidable assumptions or inaccessible facts, clearly labeled.

Include enough context for a coworker who has not read the conversation. Scale the detail to the work; omit empty categories. Use one ticket by default. Resolve whether to split it only when the work contains independently assignable outcomes with meaningful scope boundaries.

State that the design tree appears complete and use `request_user_input` to ask the user to confirm the ticket content. If they request changes, reopen only the affected branches, continue the interview, and reconfirm.

## End with the Bullet List

After confirmation, return the final ticket content as a bullet list, preserving the agreed scope, acceptance criteria, constraints, anticipated projects, conflict findings, exclusions, and labeled assumptions. For multiple agreed tickets, group each ticket's bullets under its title.

End the response at the final bullet. Do not generate an implementation plan, phased work breakdown, ordered coding steps, or a `<proposed_plan>` block, and do not request plan approval or offer to begin implementation. This workflow drafts ticket content in chat; it does not modify project files, implement the work, or create tickets in an external tracker.
