# Personal Agent Skill Library

A working MVP for agent-driven feature development. Agents investigate technical questions, implement isolated tasks and review one another. Humans approve product requirements and pull requests. The original checkout and uncommitted changes remain untouched.

## Skills

| Skill | Responsibility |
| --- | --- |
| [ticket-writer](skills/ticket-writer/SKILL.md) | Interview and inspect; produce one comprehensive approved ticket. |
| [feature-planner](skills/feature-planner/SKILL.md) | Verify initialization, isolate the feature and decompose approved scope. |
| [feature-orchestrator](skills/feature-orchestrator/SKILL.md) | Dispatch, recover, serialize reviewed squash integrations and own state. |
| [feature-implementer](skills/feature-implementer/SKILL.md) | Implement and test one scoped task in its own worktree. |
| [independent-code-reviewer](skills/independent-code-reviewer/SKILL.md) | Review actual commits independently of the author. |
| [feature-validator](skills/feature-validator/SKILL.md) | Check the integrated feature against the approved specification. |
| [pre-pr-quality-gate](skills/pre-pr-quality-gate/SKILL.md) | Audit completeness, architecture, maintainability and tests. |
| [repository-initializer](skills/repository-initializer/SKILL.md) | Initialize instructions/glossary; prepare manual releases. |
| [library-update](skills/library-update/SKILL.md) | Explicitly reconcile compatibility after manual replacement. |
| [feature-workflow](skills/feature-workflow/SKILL.md) | Shared contracts, operations and deterministic helpers. |

## Start here

Read [installation and invocation](docs/installation.md), [shared contracts](skills/feature-workflow/references/contracts.md), and [MVP limitations](docs/limitations.md). Install the entire sibling library; individual process skills depend on shared resources. This repository remains the source of truth; nothing installs or updates automatically.

Use `$repository-initializer` for an uninitialized repository, then `$ticket-writer`, `$feature-planner`, and `$feature-orchestrator`. The Orchestrator dispatches independent implementers/reviewers and runs mandatory validation and quality gates. Initial ticket and subsequent consolidated specifications require human approval. Draft PR creation follows passing gates; cleanup requires separate explicit authorization bound to a concrete resource inventory. Publication, verified merge, cleanup pending and closed are distinct states. Task/review resources can be released after integration; feature resources require verified PR merge. See the [cleanup protocol](skills/feature-workflow/references/cleanup.md).

## Validate

Working directory: repository root. Required: Python 3.10+ and Git on PATH. No Python packages are required. Tests use disposable local repositories, without remote service access. Prefer `rtk proxy python` instead of `python` when rtk is available.

**Windows PowerShell 5.1+**

```powershell
& {
    python 'scripts/validate_library.py'
    if ($LASTEXITCODE -ne 0) { throw 'Structural validation failed' }
    python -m unittest discover -s 'tests' -v
    if ($LASTEXITCODE -ne 0) { throw 'Workflow tests failed' }
}
```

**Linux Bash**

```bash
python 'scripts/validate_library.py' &&
    python -m unittest discover -s 'tests' -v
```

Tests verify protocol and Git safety. They complement independent agent review; they do not establish product correctness for future features.

See [representative scenarios](docs/scenarios.md) and the [verification results](docs/verification.md) for coverage and remaining manual checks.

## Maintain

Store skills in `skills/<skill-name>/SKILL.md`. Start from [the template](templates/SKILL.md.template), replace starter content, and link resources relatively. Keep activation, inputs, authority, procedure, outputs/completion and failure/recovery explicit. Preserve owner rules in [AGENTS.md](AGENTS.md). Keep installation-specific details in documentation.
