# Installation, invocation and manual releases

## Requirements

Use Python 3.10+, Git, and an agent environment supporting isolated worktrees and independent agents. Issue/PR publishing additionally needs an authenticated connector or supported CLI and user authorization. Helpers use Python's standard library only. Examples prefer rtk; omit only the rtk proxy prefix if it is unavailable, keeping the same failure handling. Repository maintenance scripts and tests are not installed as skills; retain this source repository to reproduce releases.

Codex discovers project skills under `<project>/.agents/skills` and user skills under `~/.agents/skills`; see the [official Codex skill documentation](https://learn.chatgpt.com/docs/build-skills). Install all ten sibling skill directories together so relative links resolve. Open Codex in the target project; restart if new skills do not appear.

## Install a new copy

Working directory: repository root. The installer creates an absent destination skills root and never overwrites. If the root already contains other skills, stage this library in a new directory, review conflicts, and manually copy its ten sibling directories and manifest. Back up any same-named folders; preserve unrelated skills.

**Windows PowerShell 5.1+**

```powershell
& {
    $skillsDestination = Join-Path "$HOME" '.agents/skills'
    rtk proxy python 'scripts/install_library.py' --destination "$skillsDestination"
    if ($LASTEXITCODE -ne 0) { throw 'Installation failed; inspect destination before retrying' }
}
```

**Linux Bash**

```bash
skills_destination="$HOME/.agents/skills"
rtk proxy python 'scripts/install_library.py' --destination "$skills_destination" || exit 1
```

For project installation, use an absolute destination ending in the existing project's `.agents/skills`. Verify the project exists first: the installer creates missing parents and cannot infer intent. Failed copies may leave a partial new destination; inspect and move it aside before retrying. Helpers never delete it or configure Codex.

## Invoke in chat

1. Use $repository-initializer when repository instructions/glossary are missing; retain its reviewed committed baseline.
2. Give $feature-planner an unstructured request or a prepared approved ticket. Planner investigates and interviews unresolved scope before approval. $ticket-writer is an optional utility for preparing one comprehensive ticket.
3. Approve the exact scope before Planner produces tasks. Valid approved scope is reused without a redundant interview or approval unless it changes. Planning does not authorize implementation dispatch.
4. Invoke $feature-orchestrator to execute the approved plan with independent implementers/reviewers, serial integration and exact-HEAD validation/quality gates. Draft PR publication also requires publishing authorization; agents never approve or merge it.
5. Return PR feedback to Orchestrator for scoped fixes, reviewed integration and renewed gates. Product changes require an approved consolidated specification revision.
6. For cleanup, inspect and explicitly authorize the concrete inventory digest. Task/review resources may be released after reviewed integration; feature worktree/branch removal additionally requires verified PR merge.

These are chat instructions, not shell commands. Product approval is separate from agent mode and execution authorization. In read-only environments prepare reviewable artifacts and defer mutations. Missing independent agents blocks dispatch rather than permitting self-review.

## Prepare a release manually

Working directory: repository root. Required: Python 3.10+, Git and rtk when available. Choose a new archive file under an existing external parent; packaging never overwrites an existing destination. Keep version/schema constants and shared contracts consistent when a release changes compatibility. Generated archives and actual verification evidence stay outside committed source.

**Windows PowerShell 5.1**

```powershell
& {
    $releaseArchive = 'C:\Work\releases\feature-skills-1.1.0.zip'
    if (-not (Test-Path -LiteralPath (Split-Path -Parent $releaseArchive) -PathType Container)) {
        throw 'Choose an existing external release directory'
    }
    rtk proxy python 'scripts/validate_library.py'
    if ($LASTEXITCODE -ne 0) { throw 'Structural validation failed' }
    rtk proxy python -m unittest discover -s 'tests' -v
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    rtk proxy python 'scripts/package_library.py' --output "$releaseArchive"
    if ($LASTEXITCODE -ne 0) { throw 'Packaging failed; inspect archive before retrying' }
}
```

**Linux Bash**

```bash
release_archive="$HOME/releases/feature-skills-1.1.0.zip"
[ -d "${release_archive%/*}" ] || exit 1
rtk proxy python 'scripts/validate_library.py' || exit 1
rtk proxy python -m unittest discover -s 'tests' -v || exit 1
rtk proxy python 'scripts/package_library.py' --output "$release_archive" || exit 1
```

The archive root contains all sibling skills and library-manifest.json with library/schema versions and SHA256 hashes for every skill resource, including snapshot.py, snapshot_model.py, the snapshot reference/schema and synthetic examples. Caches/bytecode are excluded. Installed runtime skills do not depend on repository-only scripts or tests. Hashes detect accidental differences; they are not signatures. Distribute exact-commit verification/platform evidence and limitations alongside the archive.

## Manual updates and rollback

No automatic update service exists. Quiesce active workers, back up installed sibling directories and manifest, compare against a complete release, and manually replace the library as a unit while preserving unrelated skills. Explicitly invoke `$library-update` with old/new manifests and known active feature paths. It checks compatibility and coordinates instruction-only changes; no implementation edits or unknown-schema conversion.

Keep feature workspaces outside all Git worktrees, including ignored directories. Preserve ticket/spec history and checkpoints. Rollback: stop affected agents, restore the complete library backup, and have the owning Orchestrator verify actual Git/state evidence before resuming. Never roll back product commits as an instruction shortcut.

## Consume snapshots from a separate dashboard

Keep the dashboard application, private configuration, feature workspaces and any consumer-saved snapshots outside repository worktrees. The reader uses Python 3.10+ and the standard library; it does not need a Git process or service credentials. It reports local recorded evidence only. Live agent/provider integrations belong to the separate consumer.

Use explicit repository identities and external workspace roots or individual workspaces. Root discovery examines immediate children only; it does not recursively scan or infer other locations. Use durable configured IDs across relocation and explicit workspace mappings for aliases/collisions. Paths must be absolute and native to the host.

Windows configuration example, saved as a new external JSON file:

```json
{
  "config_version": "1.0.0",
  "repositories": [{"id": "app", "path": "C:/Work/app"}],
  "workspace_roots": [{"id": "app-features", "repository_id": "app", "path": "C:/Work/workflow-data/features"}]
}
```

Linux configuration example:

```json
{
  "config_version": "1.0.0",
  "repositories": [{"id": "app", "path": "/srv/work/app"}],
  "workspace_roots": [{"id": "app-features", "repository_id": "app", "path": "/srv/workflow-data/features"}]
}
```

Working directory: any directory. Replace the quoted absolute installed-reader/config paths. These examples use rtk on PATH; omit only its proxy prefix if unavailable.

**Windows PowerShell 5.1**

```powershell
& {
    $snapshotReader = 'C:\Tools\feature-skills\feature-workflow\scripts\snapshot.py'
    $snapshotConfig = 'C:\Work\workflow-data\dashboard.json'
    rtk proxy python "$snapshotReader" --config "$snapshotConfig"
    $snapshotExit = $LASTEXITCODE
    if ($snapshotExit -notin @(0, 2)) { throw 'Snapshot configuration/input failure' }
    # Exit 2 is partial: inspect JSON completeness and diagnostics before using it.
}
```

**Linux Bash**

```bash
snapshot_reader="$HOME/.agents/skills/feature-workflow/scripts/snapshot.py"
snapshot_config="$HOME/workflow-data/dashboard.json"
snapshot_status=0
rtk proxy python "$snapshot_reader" --config "$snapshot_config" || snapshot_status=$?
case "$snapshot_status" in
    0|2) ;;
    *) exit "$snapshot_status" ;;
esac
# Exit 2 is partial: inspect JSON completeness and diagnostics before using it.
```

| Exit | Meaning |
| --- | --- |
| 0 | Complete observation; excluded initial preparation or an empty configured root is not an error. |
| 2 | Partial source results; healthy features remain available alongside explicit gaps. |
| 1 | Fatal configuration/input failure; JSON diagnostics explain it without guessed discovery. |

stdout contains one JSON envelope. Lifecycle, work phases, dependency/start readiness, blockers, feedback, activity freshness and evidence currency remain separate. A current report can still record a failed outcome. Task status, locks, PIDs or a fresh snapshot never prove an agent is live. Unknown history/approval/identity stays unavailable; the reader neither repairs nor upgrades it.

For callable use, follow the [cache-free bootstrap](../skills/feature-workflow/references/snapshot.md#cache-free-callable-bootstrap): disable bytecode before loading the reader and keep it disabled for the consumer process. A normal default import is not supported for the no-cache guarantee. The direct CLI disables sibling caching itself and needs no additional -B flag. Neither path creates a persistent cache, acquires writer locks, runs checks/cleanup or polls services.

The [normative snapshot contract and schema](../skills/feature-workflow/references/snapshot.md) define fields, stable identities, unavailable reasons, timestamps, freshness thresholds, consistency bounds, duplicate-key rejection and compatibility. Snapshot/config/visibility version 1.0.0 is independent of library version 1.1.0 and state schema 2.

New work becomes visible only after approved ticket/task production and visibility publication. Initial interviews, drafts and partial preparation stay private; later investigation and approval waits remain visible. Verified approved/planned legacy schema 2 work stays readable without adoption. Adding metadata is an explicit owner/Library Update operation with quiescence, backup, validation and limited rollback; reading never adopts it or invents old timestamps/approval.

Do not use workflow.py cleanup-status or pr-ready as read APIs: they are writer transactions and can run verification or change state. Use the separate snapshot entry point.
