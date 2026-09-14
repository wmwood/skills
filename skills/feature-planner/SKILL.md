---
name: feature-planner
description: Interview a user exhaustively through a dependency-aware design tree, confirm shared understanding, and propose an implementation plan. Use for substantial ideas or underspecified work when the user wants decisions surfaced before planning; this skill requires Plan mode and must not implement the result.
---

# Feature Planner

Build complete shared understanding before proposing a plan. Optimize for eliminating hidden assumptions, not for reaching implementation quickly.

## Require Plan Mode

Run this workflow only in Plan mode, where `request_user_input` is available.

If the current session is not in Plan mode, stop before investigating, interviewing, planning, or modifying files. Tell the user to switch Codex to Plan mode and invoke `$feature-planner` again. Do not substitute ordinary assistant-text questions and do not attempt to change modes on the user's behalf.

Plan mode is necessary but does not itself authorize implementation. This skill ends with a proposed plan for review.

## Model the Design Tree

Represent each meaningful user decision as a node. Record its prerequisites and any decisions it unlocks.

- Do not silently choose a meaningful branch for the user.
- Do not collapse alternatives merely to move faster.
- Exclude low-value implementation trivia that follows mechanically from settled decisions.
- Treat the user's answers as settled unless they explicitly reopen them.
- Let each answer add, remove, or reshape branches; do not follow a fixed questionnaire.

Maintain the tree internally unless showing it would materially help the user. The **frontier** is every unresolved decision whose prerequisites are settled.

## Interview in Dependency-Aware Rounds

At the start of each round, recompute the frontier from scratch. Ask only frontier questions; defer any question that depends on an answer still unresolved in the current round.

Use `request_user_input` for every decision question. Never ask a blocking decision as ordinary prose.

For each question:

1. State and number the decision clearly.
2. Offer mutually exclusive concrete options when the option space is knowable.
3. Put the recommended option first, label it `(Recommended)`, and explain the tradeoff concisely.
4. Preserve the tool's free-form answer path so the user may choose something else.

Ask the complete frontier together when the tool supports it. When the frontier exceeds the tool's per-call question limit, ask up to that limit as one frontier slice, wait for the answers, then recompute before asking the next slice. Do not ask a downstream question early merely to fill a slice.

After every answer set, update settled decisions and dependencies, discover any newly meaningful branches, and recompute the frontier. Continue until it is empty.

## Separate Facts from Decisions

Finding facts is Codex's responsibility; making decisions is the user's.

Inspect the available repository, filesystem, source, configuration, documentation, logs, schemas, APIs, connected tools, and relevant external sources rather than asking the user for facts Codex can determine.

When independent fact-finding can run concurrently and sub-agents are both available and authorized, delegate it. Treat an unfinished investigation as an unsettled prerequisite: hold back only its dependent questions and continue with the rest of the frontier. Do not ask the user to perform research for convenience.

Ask only for intent, preferences, constraints, or tradeoffs that cannot be safely determined from facts already available. Do not repeat answered questions or ask speculative downstream questions.

## Confirm Shared Understanding

The interview is complete only when every meaningful branch has been resolved, intentionally rejected, or marked out of scope and the frontier is empty.

Then present:

- the complete intended design;
- the important settled decisions and constraints;
- rejected and out-of-scope branches;
- any unavoidable remaining assumptions; and
- a statement that the design tree appears complete.

Use `request_user_input` to ask the user to confirm shared understanding. Do not plan until they confirm. If they do not confirm, reopen the tree and continue interviewing.

## Propose the Plan

After confirmation, inspect the environment again as needed and translate the settled design tree into a concrete, reviewable implementation plan.

The plan must:

- preserve agreed decisions, constraints, tradeoffs, and exclusions;
- organize required work into logical phases and ordered steps;
- identify dependencies and likely affected files, components, systems, APIs, schemas, migrations, infrastructure, tests, and documentation;
- include validation for each meaningful phase;
- call out relevant risks, edge cases, compatibility and migration concerns, and rollback considerations; and
- distinguish required work from optional improvements.

Do not reopen a settled decision unless implementation research reveals a real contradiction or new constraint. If that happens, return to the design tree, ask only the newly necessary decision with `request_user_input`, reconfirm shared understanding if the design materially changes, and resume planning.

Present the completed plan for review and explicitly request approval. Do not implement, modify project files, execute the plan, or take external actions under this skill. Implementation requires a separate explicit user instruction after plan approval.
