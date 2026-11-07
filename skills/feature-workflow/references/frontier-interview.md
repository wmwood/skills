# Shared frontier interview procedure

Ticket Writer and Feature Planner must use this procedure when interviewing unresolved scope. Build complete shared understanding by exposing hidden assumptions before seeking approval. The calling skill retains its own authority, artifact, approval and handoff boundaries. No mode switch is required; use an available question tool or ordinary conversation.

## Model the design tree

Represent each meaningful human decision as a node with its prerequisites, alternatives, settled answer or unresolved status, and decisions it unlocks. Maintain the tree internally unless showing it would help the human.

- Let each answer add, remove or reshape branches; explore newly meaningful alternatives rather than following a fixed questionnaire.
- Preserve meaningful alternatives until the human resolves them. Never silently choose a branch or collapse alternatives merely to finish faster.
- Treat answers as settled unless the human reopens them or new evidence reveals a contradiction or constraint. Reopen only affected branches and explain why.
- Exclude low-value implementation trivia that follows mechanically from settled decisions. Use the calling skill's scope to decide which choices belong to the human.

The **frontier** is every unresolved decision whose prerequisites are settled. An unfinished investigation is an unsettled prerequisite, even when it may eventually reveal a fact rather than require a human choice.

## Investigate facts and feed findings back

Determine accessible repository, system and related-work facts yourself using the calling skill's investigation instructions. Ask the human only for intent, preferences, constraints or tradeoffs that those facts cannot settle.

Feed conflicts requiring human intent back into the tree before confirmation. Recheck affected contracts, consumers and relationships when an answer materially changes scope. Distinguish verified contradictions from plausible risks and label inaccessible facts instead of inventing them.

While investigation is unfinished, hold back only dependent questions and continue with the rest of the frontier. An access gap does not settle its dependent decisions: investigate alternatives, or ask the human to resolve the resulting scope or tradeoff. Preserve unavoidable factual unknowns explicitly in the final draft.

## Interview in frontier rounds

1. Recompute the entire frontier from scratch at the start of each round.
2. Ask the complete frontier together when the question tool or conversation format supports it. Respect the tool's per-call limit by asking one frontier slice, waiting for answers, then recomputing before the next slice.
3. Ask only frontier questions. Defer questions depending on any unresolved answer, including another question in the same round; never add downstream questions merely to fill a slice.
4. After every answer set, update settled decisions and prerequisites, discover newly meaningful branches and recompute the frontier. Continue until the completion gate is satisfied.

For every decision question:

- Clearly identify and number the decision.
- Offer concrete, mutually exclusive options when the option space is knowable.
- Put the recommended option first, label it `(Recommended)`, and explain its tradeoff concisely.
- Preserve a free-form answer path, through the tool or an ordinary reply, so the human can choose another approach.

Use an available question tool that supports the needed exchange; ordinary conversation is a valid fallback. Wait for answers before dependent work. Unanswered questions, elapsed time and suggested defaults never settle a decision or supply approval. Avoid repeating settled questions.

## Complete the interview and confirm scope

The interview is complete only when every meaningful branch has been resolved, intentionally rejected or explicitly marked out of scope, and the frontier is empty. An empty frontier with blocked unresolved decisions is not completion.

Present the calling skill's complete ticket or scope draft, including intended behavior and acceptance criteria, settled decisions and constraints, rejected or excluded branches, and unavoidable factual assumptions or access gaps. State that the design tree appears complete and ask the human to approve that exact content. This is the calling skill's existing scope approval, not an additional approval stage.

If the human requests changes or does not confirm shared understanding, reopen only affected branches, continue the interview and reconfirm the revised complete draft. Follow the calling skill's approval-evidence requirements before its next phase.

## Reuse approved scope and respond to new evidence

Feature Planner reuses a prepared ticket when its exact scope and approval evidence remain valid; do not repeat settled questions or request redundant approval. Assess reuse against accessible evidence without inventing an interview-history requirement for previously approved tickets.

If investigation or planning reveals a meaningful gap, contradiction or new constraint, return affected decisions to the tree and resume frontier rounds. Preserve unaffected answers. Obtain approval of the changed consolidated scope before continuing dependent planning, using the calling skill's existing specification and history rules.
