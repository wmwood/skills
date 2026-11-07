---
name: library-update
description: Manually reconcile instruction compatibility after installed feature skills have been overwritten, inspecting active feature state without changing implementation code.
---

# Library Update

## Activation and inputs
Run only when the user explicitly invokes this update workflow after manually replacing installed skills. Inputs: old manifest or backup, new manifest and installed skill root, and known active feature workspace paths. Read [contracts](../feature-workflow/references/contracts.md) and [operations](../feature-workflow/references/operations.md). No background monitor, automatic installation or global filesystem scan.

## Authority and procedure
1. Verify all installed sibling resources against the new release manifest; compare old/new hashes, library version, schema, authority and instruction contracts. An absent old manifest is unknown compatibility, never proof of safety.
2. Inventory active workspaces from supplied paths and connected session evidence. Inspect actual schema, pinned library version, ticket/spec digests, task ownership, worktrees, checkpoint generation, locks, in-flight reviews, integration and gate evidence. Ask for workspace locations only when they cannot be found in available session context.
3. Coordinate quiescence with each owning Orchestrator before migration; do not race live agents or remove their locks. Save a unique external backup/checkpoint and explain concrete compatibility effects. Unknown major/schema versions block resumption until a supported migration is designed and reviewed.
4. For compatible changes, propose only repository instruction or glossary diffs in an isolated worktree. Never modify implementation code, tests, dependencies, build/configuration files, original ticket, approved specification history, or task commits to make the new library fit. Product changes return to the human requirements process.
5. Review instruction changes independently and have the owning Orchestrator serialize their integration. Migrate state only with a documented supported transformation, backup, schema validation and explicit evidence of preserved requirements/ownership. If none exists, leave state intact and report a blocked migration; this MVP supplies no generic schema converter.
6. Recheck instruction hashes, actual Git heads and active task evidence. Invalidate affected reviews/gates, update the pinned version only after reconciliation, and hand recovery context to the single owning Orchestrator. Do not independently resume or integrate task branches.

## Outputs and completion
Return compatibility classification, inspected workspaces, missing evidence, reviewed instruction-only changes, checkpoint/backup paths, required revalidation and rollback procedure. Completion means compatibility has been demonstrated for the inspected workspaces; never claim uninspected features are safe.

## Failure and recovery
Mixed/missing release files, unknown schema, changed requirements, implementation edits or live writers stop dependent migration. Restore only this attempt's instruction/state changes from verified backups after checking no newer writer exists. Preserve backups and branch/worktree evidence; do not roll back product commits or overwrite installed skills. Report the precise manual action needed to recover.
