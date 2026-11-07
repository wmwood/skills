---
name: repository-initializer
description: Initialize repository instructions and glossary safely in an isolated worktree, or manually prepare and validate a release of this skill library.
---

# Repository Initializer

## Activation and inputs
Use when asked to initialize a repository for feature work or manually prepare a library release. Inputs: repository path, committed baseline, existing owner instructions, and requested initialization or release scope. Read the [shared contract](../feature-workflow/references/contracts.md) and [operations](../feature-workflow/references/operations.md). Requires Git; release helpers require Python 3.10+.

## Authority and procedure
For initialization, inspect existing instructions, architecture, glossary, tests, commands and actual Git status. Preserve the original checkout and its uncommitted work. Create a uniquely named branch and absent external worktree from the committed baseline; never switch, stash, reset, or clean the original checkout. If creation partially fails, inventory the actual branch/worktree before any retry. Do not reuse an existing path.

Create or narrowly extend AGENTS.md with verified setup/check commands, architecture constraints, ownership and feature-workflow boundaries. Create or extend GLOSSARY.md with canonical terms, meanings, code aliases and source evidence. Preserve owner rules and conflicting terms for resolution. Investigate technical facts; ask humans only about product vocabulary or business choices. Independently review the instruction diff, verify commands safely, commit on the initializer branch and return a reviewable handoff. Do not merge into the original checkout or implement product code. Planner may start only from a committed baseline containing the reviewed initialization.

For manual release preparation of this library, inspect the intended diff, version/schema compatibility and all required sibling skills. Run structural validation and the full test suite, then use the repository's packaging helper to create a new archive with content hashes. Follow repository installation documentation; these repository-only helpers are not dependencies of installed skills. Record version, commit, checks, platform coverage, archive path and limitations. Do not publish, install, overwrite a release archive or synchronize skills automatically.

## Outputs and completion
Initialization: isolated branch/worktree, reviewed AGENTS.md and GLOSSARY.md, command evidence and next-step instructions. Release: validated archive and embedded manifest, compatibility summary and test evidence. Approval and merge authority remain with the human or the authorized owning workflow.

## Failure and recovery
Missing Git baseline, contradictory owner rules, failed checks or unavailable tools block the affected operation. Preserve original files and evidence; never invent a successful check. Reconcile partial creation using Git worktree/ref evidence before retry. Release failures leave installation untouched; remove only a newly created incomplete archive that this attempt owns, or preserve it for inspection.
