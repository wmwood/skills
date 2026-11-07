---
name: pre-pr-quality-gate
description: Perform the mandatory independent feature-level audit of completeness, maintainability, architecture, duplication, terminology and tests before draft PR creation.
---

# Pre-PR Quality Gate

## Activation and inputs
Use before a draft PR and after changes that invalidate the prior gate. Inputs: integrated feature HEAD/base, latest approved consolidated spec/revision/digest, repository instructions/glossary, complete feature diff, review and validation evidence, and report destination. Read the [shared contract](../feature-workflow/references/contracts.md) and [shared operations](../feature-workflow/references/operations.md).

## Authority
Independently audit the whole feature. Do not implement fixes while certifying them, change product requirements, integrate, write canonical state, approve/merge a PR or waive the gate. Do not certify your own implementation; ask Orchestrator to assign an independent auditor if necessary.

## Procedure
1. Verify exact integrated HEAD/latest approved spec and inspect the full feature diff, surrounding architecture and acceptance coverage. Confirm every task has independent review and verified integration, and feature validation is current.
2. Audit completeness against approved requirements, maintainability and unnecessary complexity, architecture/interface consistency, duplicated logic and avoidable abstractions, domain vocabulary versus GLOSSARY.md, and test quality including meaningful failure/negative cases and overmocking. Inspect documentation and operational/migration implications relevant to this feature.
3. Distinguish concrete blocking defects from optional improvements. For each finding give location, consequence and evidence; do not expand scope with speculative redesigns or silently alter requirements.
4. Run relevant safe checks when needed; use an isolated audit worktree if they mutate files. Record commands/results and required evidence gaps.
5. Write an immutable report with auditor identity, exact HEAD, spec revision/digest, all six audit dimensions, findings, check evidence and passed status. Follow the [helper report interface](../feature-workflow/references/cli.md): required fields are `agent`, `head`, `spec_revision`, Boolean `passed`, and nonempty `evidence` containing audit coverage and commands/results/report paths. Pass only when no blocking issues or required evidence gaps remain. Recheck HEAD/spec before submission and return the verdict to Orchestrator.

## Outputs and completion
An independent mandatory quality report on the exact current feature state. A pass authorizes no external action by itself: Orchestrator still verifies every gate, publishing authority and draft-only publication.

## Failure and recovery
Blocking findings become scoped repair work through Orchestrator, then independent review, squash integration and refreshed validation/gate evidence. Missing evidence blocks a pass. Preserve interrupted reports as partial; a new commit or spec invalidates prior certification. Never waive the audit because a deadline or earlier task review passed.

## Visibility reporting
Report observed audit activity/time, known chat references, explicit blockers and resolution conditions, and any human feedback question/artifact/affected work using the [recording shapes](../feature-workflow/references/snapshot.md#recording-extension). Orchestrator ingests these observations; you do not write canonical status or infer liveness. Feedback resolution never waives independent exact-HEAD quality evidence.

## Resource handoff
Report every created worktree/branch, temporary directory and full container/network ID with owner, purpose, exact path, source HEAD and task ID immediately to Orchestrator for the feature manifest. Include resources and unrecorded creation attempts in interruption reports. Supply durable report paths and retention needs before releasing a worktree; only Orchestrator performs explicitly authorized cleanup under the [cleanup protocol](../feature-workflow/references/cleanup.md). Keep application/shared resource ownership explicit.
