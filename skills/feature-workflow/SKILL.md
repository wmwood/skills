---
name: feature-workflow
description: Shared feature workflow contracts and operations, including configured read-only JSON snapshots; use for repository intelligence, state, context, Git, glossary, or publishing support.
---

# Feature Workflow Utilities

## Activation and inputs
Use for a process skill or a configured local status consumer. Authorized writer inputs are repository, approved scope, role identity and external workspace; read-only snapshot inputs are explicit repository/workspace configuration and need no writer role or approval. Requires Python 3.10+; Git is required only for writer operations that use it. This utility never assumes orchestration authority.

## Authority and procedure
Read [contracts](references/contracts.md) before creating state or transferring work. Read [operations](references/operations.md) for reusable investigation, Git, context, publication, and glossary procedures. Use [workflow.py](scripts/workflow.py) only for authorized deterministic writer operations; [CLI reference](references/cli.md) defines requests, typed visibility recording and recovery. For read-only status, use [snapshot.py](scripts/snapshot.py) with explicit external configuration and the [snapshot contract](references/snapshot.md#cli-and-platform-checks). Its CLI is the safe default. Callable consumers must follow the [cache-free bootstrap](references/snapshot.md#cache-free-callable-bootstrap) before loading the reader; arbitrary default import is not a supported cache-free invocation. Snapshot reads do not acquire writer locks, mutate state/generation, adopt metadata, run Git/subprocesses/tests/services or perform cleanup. Legacy projection needs no migration. Read the [cleanup protocol](references/cleanup.md) when registering resources, planning or executing cleanup, or reporting closeout. Process skills own decisions; utilities implement operations within their caller's authority.

## Outputs and completion
Return objective evidence, artifact paths, unavailable-data reasons and unresolved constraints. Keep lifecycle, dependency readiness, explicit blockers, feedback and activity freshness distinct; assignment/task status never proves a running agent. A helper success is not human approval, independent review, or feature completion.

## Failure and recovery
For reader failures, retain healthy source results and explicit diagnostics/partial availability without attempting repair, adoption or cleanup. For conflicting writer state, missing authority, incompatible schema, dirty managed worktree, or ambiguous Git evidence, stop the dependent operation and preserve artifacts. Reconcile from actual Git and checkpoint evidence before retrying; never reset the original checkout.
