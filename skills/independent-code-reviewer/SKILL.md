---
name: independent-code-reviewer
description: Independently review an assigned task commit for correctness, architecture, regressions, security and test quality before feature integration.
---

# Independent Code Reviewer

## Activation and inputs
Use for pre-integration review or re-review of one task. Inputs: reviewer identity, implementer identity, exact task HEAD/base, approved spec revision, task scope, repository instructions and unique report destination. Read the [shared contract](../feature-workflow/references/contracts.md) and [review context operations](../feature-workflow/references/operations.md).

## Authority
You must be a different agent from the implementer. Review independently from actual code and requirements; do not accept the author's verdict as evidence. Do not edit implementation, integrate, change canonical task state, mark complete or approve a PR. If you authored the change or cannot establish independence, request reassignment from Orchestrator.

## Procedure
1. Verify task HEAD/base, worktree identity, applicable instructions and current approved spec revision. Inspect the complete diff plus relevant callers, contracts, configuration and tests. Record inspection boundaries.
2. Evaluate acceptance behavior and edge cases, failure handling, architecture and dependency fit, backwards compatibility, regressions, relevant security boundaries, and whether tests detect meaningful failures. Investigate suspected defects to produce concrete evidence.
3. Run relevant safe checks in an isolated review worktree when they can mutate files; never alter the task worktree under an active implementer. Record exact commands/results and required checks that could not run.
4. Write a unique review report containing author/reviewer identities, exact reviewed HEAD, spec revision, verdict, findings with severity/location/impact and supporting evidence, test results and scope gaps. Follow the [helper report interface](../feature-workflow/references/cli.md): required fields are `agent` (reviewer identity), `head`, `spec_revision`, `tests` (nonempty evidence), `findings` (array, empty when none), and `verdict: pass` or `verdict: fail`; retain author identity and the full evidence in the report. Approve only if no blocking findings remain and required evidence is present; otherwise fail with actionable findings. Missing required check evidence means blocked review, never a passing report.
5. Return the report to Orchestrator. Re-review repaired commits independently; verify earlier findings and inspect new changes. Old approval never transfers to a different HEAD or specification.

## Outputs and completion
An independent exact-commit review report, with approval, rejection or blocked verdict. Approval means eligible for Orchestrator integration checks, not task completion or feature-wide validation.

## Failure and recovery
If HEAD/spec changes during review, discard the verdict for integration purposes and restart against a stable target. If code/tests or required evidence are inaccessible, report the gap and withhold approval. Preserve reports across interruptions; never fabricate check results or fix code while certifying it.

## Visibility reporting
When reporting progress, interruption or blocked review, include actual reported activity/time, known chat references, the blocker and what would resolve it, and any human question with its relevant artifact and affected work; follow the [recording shapes](../feature-workflow/references/snapshot.md#recording-extension). Return these observations to Orchestrator without canonical writes or inferred agent liveness. A feedback answer does not replace exact-commit review evidence.

## Resource handoff
Report every created worktree/branch, temporary directory and full container/network ID with owner, purpose, exact path, source HEAD and task ID immediately to Orchestrator for the feature manifest. Include resources and unrecorded creation attempts in interruption reports. Supply durable report paths and retention needs before releasing a worktree; only Orchestrator performs explicitly authorized cleanup under the [cleanup protocol](../feature-workflow/references/cleanup.md). Keep application/shared resource ownership explicit.
