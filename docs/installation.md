# Installation, invocation and manual releases

## Requirements

Use Python 3.10+, Git, and an agent environment supporting isolated worktrees and independent agents. Issue/PR publishing additionally needs an authenticated connector or supported CLI and user authorization. Helpers use Python's standard library only. Repository maintenance scripts and tests are not installed as skills; retain this source repository to reproduce releases.

Codex discovers project skills under `<project>/.agents/skills` and user skills under `~/.agents/skills`; see the [official Codex skill documentation](https://learn.chatgpt.com/docs/build-skills). Install all ten sibling skill directories together so relative links resolve. Open Codex in the target project; restart if new skills do not appear.

## Install a new copy

Working directory: repository root. The installer creates an absent destination skills root and never overwrites. If the root already contains other skills, stage this library in a new directory, review conflicts, and manually copy its ten sibling directories and manifest. Back up any same-named folders; preserve unrelated skills.

**Windows PowerShell 5.1+**

```powershell
& {
    $skillsDestination = Join-Path "$HOME" '.agents/skills'
    python 'scripts/install_library.py' --destination "$skillsDestination"
    if ($LASTEXITCODE -ne 0) { throw 'Installation failed; inspect destination before retrying' }
}
```

**Linux Bash**

```bash
skills_destination="$HOME/.agents/skills"
python 'scripts/install_library.py' --destination "$skills_destination"
```

For project installation, use an absolute destination ending in the existing project's `.agents/skills`. Verify the project exists first: the installer creates missing parents and cannot infer intent. Failed copies may leave a partial new destination; inspect and move it aside before retrying. Helpers never delete it or configure Codex.

## Invoke in chat

1. `$repository-initializer`: inspect this repository and propose AGENTS.md/GLOSSARY.md initialization in an isolated worktree.
2. `$ticket-writer`: investigate my feature and interview me about unresolved product decisions; produce one comprehensive ticket.
3. Approve the exact ticket; `$feature-planner`: plan this approved ticket with an external feature workspace.
4. `$feature-orchestrator`: execute the approved plan with independent implementers/reviewers, serial integration, validation and a draft PR after all gates pass.
5. Give PR feedback to the same Orchestrator for scoped fixes and renewed review/gates.
6. For cleanup, inspect the concrete inventory and explicitly authorize named artifacts. Remove task/review resources incrementally only after integration; remove feature branch/worktree only after verified PR merge. Approval must match the cleanup inventory digest.

These are chat instructions, not shell commands. Loading skills does not require Plan mode; respect the active environment's execution restrictions. In a read-only/Plan session prepare reviewable work and defer mutations until execution is permitted. Product approval is separate from mode selection. Missing independent agents blocks dispatch rather than permitting self-review.

## Prepare a release manually

Working directory: repository root. Required tools as above. Choose a new archive path with an existing parent; packaging never overwrites. Update version/schema constants and shared contract together for compatibility changes. Generated releases belong outside committed source; these examples use ignored `outputs`.

**Windows PowerShell 5.1+**

```powershell
& {
    python 'scripts/validate_library.py'
    if ($LASTEXITCODE -ne 0) { throw 'Structural validation failed' }
    python -m unittest discover -s 'tests' -v
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    New-Item -ItemType Directory -Path 'outputs' -Force -ErrorAction Stop | Out-Null
    python 'scripts/package_library.py' --output 'outputs/feature-skills-1.1.0.zip'
    if ($LASTEXITCODE -ne 0) { throw 'Packaging failed; inspect archive before retrying' }
}
```

**Linux Bash**

```bash
python 'scripts/validate_library.py' &&
    python -m unittest discover -s 'tests' -v &&
    mkdir -p -- 'outputs' &&
    python 'scripts/package_library.py' --output 'outputs/feature-skills-1.1.0.zip'
```

The archive root contains all sibling skill directories and `library-manifest.json`, with library/schema version and SHA256 hashes for each skill resource. Caches/bytecode are excluded. Hashes detect accidental differences; they are not signatures. Distribute validation/platform results and limitations alongside the archive.

## Manual updates and rollback

No automatic update service exists. Quiesce active workers, back up installed sibling directories and manifest, compare against a complete release, and manually replace the library as a unit while preserving unrelated skills. Explicitly invoke `$library-update` with old/new manifests and known active feature paths. It checks compatibility and coordinates instruction-only changes; no implementation edits or unknown-schema conversion.

Keep feature workspaces outside all Git worktrees, including ignored directories. Preserve ticket/spec history and checkpoints. Rollback: stop affected agents, restore the complete library backup, and have the owning Orchestrator verify actual Git/state evidence before resuming. Never roll back product commits as an instruction shortcut.
