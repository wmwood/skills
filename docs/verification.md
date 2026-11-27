# Verification conventions

Working directory: repository root. Required tools: Python 3.10+, Git, and rtk when available. The library validator checks frontmatter, relative links, unfinished placeholders and shell coverage. Unit tests use disposable repositories and paths with spaces, never live PR services or the original target checkout. Docker tests mock daemon responses; live Docker behavior requires separate environment-specific verification.

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

Tests cover exact and replacement inventory authorization, gate and review attempt evidence, build-output attribution, native Windows named streams, interruption during file, worktree or branch removal, recovery refs, merge-gated feature removal, and shared Docker ownership. Record unavailable platforms and privilege-dependent skips in the delivery report. Keep completed feature verification results in Git history and PR evidence; this document contains reusable development conventions only.
