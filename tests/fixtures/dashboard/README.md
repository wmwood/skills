# Synthetic dashboard acceptance fixtures

These files contain invented scope, approval, agent, chat and provider evidence.
They are test inputs, not authorization or history for a real feature.

- base-state.json is a small approved/planned schema 2 source with an opt-in visibility marker.
- artifacts.json supplies deterministic UTF-8 bytes for its local references. Recorded ticket/specification hashes match those synthetic bytes.
- catalog.json defines named state mutations, additional/missing files, raw malformed input, acceptance IDs, and explicit expected public snapshot fields and diagnostic codes. Expectations were chosen from the approved contract rather than captured/blessed from runtime output.
- test_dashboard_acceptance.py materializes the inputs in disposable external directories and exercises the public callable and CLI. It retains no consumer cache and commits no runtime output.

The expected snapshot views deliberately name consumer-visible semantics rather than copying opaque raw source records. Each listed JSON Pointer has an exact expected value. Required diagnostic codes must be present; explicitly forbidden codes must be absent. Tests separately verify deterministic complete output, state byte digests, all acceptance mappings, and unchanged filesystem/generation/lock/runtime bytes. Empty or unavailable evidence is not normalized into success.

The callable clock is fixed at 2026-11-06T20:00:00Z. Only CLI generation/observation time is allowed to be real; CLI tests compare stable completeness/exit semantics without rewriting time-sensitive evidence. Host-native temporary absolute paths are supplied explicitly; tests compare them to the actual configured locations. No identity, status, provenance, digest, approval or error code is normalized away.

Deterministic concurrency tests call the public build_snapshot interface while injecting a concurrent writer at the reader's observation boundary. These fixture writes are test fault injection, not permitted reader mutations. Separate guard tests forbid write APIs, processes and networking throughout ordinary reads. CLI subprocesses invoke only the reader; Windows junction setup uses the platform's junction-creation command outside the read path.

Direct Planner interviewing and human decision quality require the role-guidance task's manual behavioral walkthrough. The catalog records this required manual evidence instead of claiming state fixtures prove an agent will follow prose. Existing writer-role tests provide separate executable ownership evidence.

PowerShell 5.1 and Linux Bash use the same Python test entry point and argument syntax; see the repository verification instructions for exit handling. Execution on Windows does not claim Linux coverage. The suite runs a real Windows junction test on Windows, a real POSIX read-only-mode test on POSIX, and reports unavailable capabilities as skips. Injected PermissionError coverage is identified separately and does not claim Windows ACL enforcement.
