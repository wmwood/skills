# Verification conventions

Working directory: repository root. Required tools: Python 3.10+, Git, and rtk when available. The library validator checks frontmatter, relative links, unfinished placeholders and shell coverage. Unit tests use disposable repositories and paths with spaces, never live PR services or the original target checkout. Snapshot configuration and workflow fixtures must be outside every Git checkout; an ignored repository tmp directory is not an external feature workspace. Docker tests mock daemon responses; live Docker behavior requires separate environment-specific verification.

**PowerShell 5.1**
```powershell
rtk proxy python "scripts/validate_library.py"
if ($LASTEXITCODE -ne 0) { throw "Library validation failed" }
rtk proxy python -m unittest discover -s "tests" -v
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
```

**Linux Bash**
```bash
rtk proxy python "scripts/validate_library.py" || exit 1
rtk proxy python -m unittest discover -s "tests" -v || exit 1
```

The workflow suite covers exact inventory authorization, squash source preservation, interrupted/repeated cleanup, dirty/ignored files, changed branches, merge-gated feature worktree removal and shared Docker ownership.

Snapshot checks cover recorded approval/visibility boundaries, structured feedback and blockers, dependency-derived readiness, unknown liveness, freshness, stable artifact identity and evidence currency. Reader/CLI and synthetic acceptance checks verify configured containment/identity, partial source results, bounded consistent reads, malformed/unsupported/missing/stale data, and unchanged files/generation/locks.

Verify both installed entry points from a fresh process: direct CLI and the supported callable bootstrap with bytecode disabled before loading. Record before/after file and directory fingerprints; deleting a cache afterward is not nonmutation evidence. Full details and consumer setup are in the [snapshot contract](../skills/feature-workflow/references/snapshot.md).

Library tests verify the distributed schema/examples/runtime resources and manifest hashes, existing-destination refusal, and reader operation without repository-only scripts. Use safe disposable destinations with spaces and external configuration/workflow inputs. Do not install into actual skill collections or overwrite a release for verification. Record unavailable platforms and privilege-dependent skips in the delivery report. Keep completed feature verification results in Git history and PR evidence; this document contains reusable development conventions only.


For each delivery, preserve the inspected commit, exact commands/results, platform/version, privilege-dependent skips and acceptance mapping in an external report. Do not copy private workspace paths, actual chat/approval data, generated snapshots or run-specific counts into reusable documentation. Missing required feature evidence blocks validation; local task tests do not replace independent exact-HEAD review, feature validation or the separate quality gate.
