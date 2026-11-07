# Known MVP limitations, prioritized

1. **Cooperative authority.** Instructions and state checks are not authentication or a sandbox. Direct filesystem/Git access can bypass helpers; inspect human approval provenance and distinct agent identity. Use environment permissions where appropriate.
2. **Local coordination.** A single canonical writer and local lock/checkpoints are not distributed transactions. Ambiguous interrupted operations require evidence-based Orchestrator recovery; no automatic stale-lock breaking. Cleanup execution journals per-item progress; unresolved errors remain blocked. Docker absence is verified through successful daemon listing before retry reconciliation. Directories are removed only when empty.
3. **Compatibility.** Releases include hashes/version/schema. Unknown schemas/major versions block. No generic migration converter, automatic installer/update, background watcher or global feature registry.
4. **Publishing.** Live issue/PR publication requires authorization, authentication and service availability. Local tests do not publish. PR approval/merge remain human-owned.
5. **Agent judgment.** Skills are instructions interpreted by an agent, rather than a self-executing workflow engine. Scenarios validate deterministic safety and contracts; complex product behavior still requires independent review, feature validation and quality assessment against real acceptance criteria.
6. **Platforms.** Helpers use portable Python and subprocess Git. Record actual shell coverage; unavailable Linux Bash receives static review only. Repository hooks/tool availability vary.
7. **Installation.** The installer creates a new skills root only. Existing collections require reviewed manual copying/backups. Development does not install outside this repository.
