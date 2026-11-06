# Working in this repository

This repository is the source of truth for the owner's personal AI skills.

## Shell commands

Prefer `rtk` when running external commands to reduce output. Prefix each external command separately in a chain. In both PowerShell and Bash, use `rtk proxy <cmd>` when raw output is needed but usage should still be tracked. Run shell built-ins and PowerShell cmdlets directly; they are not standalone executables that `rtk` can invoke.

All READMEs, skill instructions, references, and templates containing shell commands must support Windows PowerShell 5.1 and Linux Bash:

- Provide clearly labeled `powershell` and `bash` blocks for shell-specific syntax. Identical commands may share one block labeled **PowerShell and Bash**.
- Quote paths and document the working directory and required tools. Do not use PowerShell 7-only syntax in PowerShell examples.
- Preserve equivalent behavior, including failure handling. Creation examples must stop when the destination already exists without overwriting its contents.
- State limitations for platform-specific operations and provide an alternative where available; do not invent unsupported equivalents.

## Skill conventions

- Store each skill in `skills/<skill-name>/SKILL.md`.
- Use lowercase letters, digits, and hyphens for skill names, under 64 characters. Match the folder name and frontmatter `name`.
- Include YAML frontmatter with `name` and a concise `description` describing the capability and when it applies.
- Start new skills from `templates/SKILL.md.template` and replace all starter content before treating them as finished.
- Keep instructions focused on the owner's workflow. Preserve the requested scope and existing authorization boundaries.
- Add `references/`, `scripts/`, `assets/`, or agent-specific metadata only when needed. Link supporting resources from the instructions using relative paths.
- Keep application-specific installation details separate from otherwise portable instructions.
- Do not install or synchronize skills outside this repository unless requested.

## Verification

For skill edits, check frontmatter, relative links, unfinished placeholders, and command coverage for both shells. Verify changed command examples in available shells with safe temporary inputs, including paths with spaces and existing destinations where relevant. Report any platform receiving only static review. Try representative requests when behavioral validation would help. Run any new or modified helper scripts with safe sample inputs before delivering them. Do not add a test framework for prose-only changes.

Do not commit secrets, private task data, or generated output. Preserve unrelated work already in the repository.

## Repository architecture and setup

This is a library of agent instructions and portable safety helpers, not an application or a self-running workflow engine. Read [GLOSSARY.md](GLOSSARY.md) for repository terminology.

- `skills/` contains the installable sibling skills. Shared workflow authority and state semantics live in [the workflow contract](skills/feature-workflow/references/contracts.md); consult it before changing any process role, state transition, approval or compatibility behavior.
- [Shared operations](skills/feature-workflow/references/operations.md), [the helper interface](skills/feature-workflow/references/cli.md) and [cleanup protocol](skills/feature-workflow/references/cleanup.md) define context handoffs, deterministic helper inputs and resource retention. Keep instructions and helper behavior consistent when changing these interfaces.
- `scripts/` contains repository-only validation, packaging and installation utilities. Installed skills must not depend on those repository-only scripts. `tests/` exercises helpers in disposable repositories and directories; `docs/` contains usage and verification guidance.
- Work from an explicit committed baseline in an isolated worktree. Preserve the original checkout and its index, tracked edits and untracked files. Keep private tickets, specifications, state, reports and checkpoints in external feature workspaces outside every repository worktree, even when an in-tree path would be ignored.

Development requires Python 3.10+ and Git on PATH. The helpers use the Python standard library; no package installation is needed. The command examples below additionally require `rtk` on PATH. If unavailable, omit only the `rtk proxy` prefix and preserve the same exit-code handling.

## Workflow ownership

Humans approve product scope and requirements revisions, approve/merge PRs, and authorize cleanup against a concrete inventory digest. A proposed change or an unanswered question is not approval.

Planner owns initial planning state and hands canonical ownership to Orchestrator. After that handoff, Orchestrator alone writes canonical state, integrates task branches and marks tasks complete. Implementers, reviewers, validators and quality auditors write separate evidence reports; independent reviewers and gate agents must not certify their own implementation. These roles are a cooperative protocol, not authentication.

Preserve the original ticket and approved specification history. Tie review and gate evidence to the exact commit and approved specification revision. New commits or requirements can invalidate that evidence. Publication, verified merge and cleanup completion remain distinct. Follow the shared contract for detailed authority and transition rules rather than introducing another state definition here.

Repository initialization changes instructions and glossary in its own worktree and returns a reviewed commit; it does not merge, install skills, or implement the feature being prepared. Later instruction/glossary changes follow the owning feature's review and integration process.

## Development checks

Working directory: repository root, including an isolated checkout of this repository. Required tools: Python 3.10+, Git and `rtk` on PATH as described above. Run the structural validator for instruction edits. Run the existing tests when changing helpers or their contracts, and when verifying these check commands. Tests create disposable resources; they do not publish PRs or install into the user's skill directories. Do not use a live feature workspace as test input.

**Windows PowerShell 5.1**

```powershell
& {
    rtk proxy python "scripts/validate_library.py"
    if ($LASTEXITCODE -ne 0) { throw "Library validation failed" }
    rtk proxy python -m unittest discover -s "tests" -v
    if ($LASTEXITCODE -ne 0) { throw "Workflow tests failed" }
}
```

**Linux Bash**

```bash
rtk proxy python "scripts/validate_library.py" || exit 1
rtk proxy python -m unittest discover -s "tests" -v || exit 1
```

Record actual platform coverage. Git Bash on Windows does not establish Linux coverage. Docker scenarios use mocked service responses and do not establish live daemon behavior. See [verification conventions](docs/verification.md) for the existing suite's boundaries.
