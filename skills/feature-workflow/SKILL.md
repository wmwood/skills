---
name: feature-workflow
description: Shared operations and contracts for the modular feature development skills; use when one of those skills needs repository intelligence, state, Git, context, glossary, or publishing operations.
---

# Feature Workflow Utilities

## Activation and inputs
Use on request from a process skill. Inputs are the repository, approved feature scope, role identity, and external workspace path. Requires Git and Python 3.10+. This utility never assumes orchestration authority.

## Authority and procedure
Read [contracts](references/contracts.md) before creating state or transferring work. Read [operations](references/operations.md) for reusable investigation, Git, context, publication, and glossary procedures. Use [workflow.py](scripts/workflow.py) for deterministic state and Git safety checks; [CLI reference](references/cli.md) defines requests and recovery. Read the [cleanup protocol](references/cleanup.md) when registering resources, planning or executing cleanup, or reporting closeout. Process skills own decisions; utilities implement operations within their caller's authority.

## Outputs and completion
Return objective evidence, artifact paths, and unresolved constraints to the caller. A helper success is not human approval, independent review, or feature completion.

## Failure and recovery
On conflicting state, missing authority, incompatible schema, dirty managed worktree, or ambiguous Git evidence, stop the dependent operation and preserve artifacts. Reconcile from actual Git and checkpoint evidence before retrying; never reset the original checkout.
