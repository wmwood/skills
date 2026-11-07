# Dashboard snapshot contract 1.0.0

This is the consumer and recording contract for a separate local dashboard. The library supplies JSON and workflow reporting; it does not host a dashboard. Authority remains in [the workflow contract](contracts.md). The machine-readable output schema is [snapshot-schema.json](snapshot-schema.json). [Complete](../assets/snapshot-examples/complete.json), [partial](../assets/snapshot-examples/partial.json), and [unavailable](../assets/snapshot-examples/unavailable.json) envelopes contain synthetic data only.

## Versions and compatibility

Output `contract_version` is `1.0.0`, independently versioned from producer library version and source state schema. A consumer accepts understood 1.x fields, ignores unknown optional fields, and rejects an unsupported major version. Unknown status values remain null with an `unsupported` unavailable entry and `UNKNOWN_STATUS` diagnostic; never guess a transition. The schema fixes major 1 and documents 1.0 fields.

The supported input is state schema 2 and library major 1. New writer metadata is the optional `state.visibility` extension with `version: "1.0.0"`; it does not change the meanings of existing state fields. Metadata absence is legacy data, not an empty, freshly reported collection. Other source schemas, library majors, or visibility majors are unsupported. Adding compatible metadata must not silently upgrade pinned workspaces. A writer may explicitly adopt the extension only under the existing owner/Library Update protocol after quiescence, a unique external backup, validation and documented rollback. Readers never adopt or migrate. Unknown history remains absent; an adoption time is only the actual recording time. Keeping a legacy workspace read-only without adoption is supported.

## Configuration and identity

The UTF-8 configuration is an object with these fields:

| Field | Type and meaning |
| --- | --- |
| `config_version` | `"1.0.0"`; unsupported majors are fatal configuration errors. |
| `repositories` | Nonempty array of `{id, path}`: stable owner-assigned ID and absolute repository location. |
| `workspace_roots` | Array of `{id, repository_id, path}`: explicit absolute external roots. Discover immediate child directories containing `state.json` only; no recursive/global scan. |
| `workspaces` | Array of `{id, repository_id, path}`: explicit workspace and stable workspace-ID override, including relocation aliases. |
| `freshness_seconds` | Positive integer, default 3600; the effective value appears in every projected activity. |
| `max_read_attempts` | Integer 1 through 3, default 3; total attempts, not retries after the first attempt. |

Both location arrays default to empty; at least one must be nonempty. IDs are case-sensitive strings matching `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`. Paths must be absolute host-native paths; do not translate a Windows drive into a Linux path or vice versa. Configuration lives outside repository worktrees. Repository identity is explicit configuration, not a remote URL, checkout folder name or Git subprocess lookup. Record repository paths as metadata; the reader does not invoke Git or require a worktree to be online.

Multiple paths with the same explicit workspace ID and repository ID are aliases. If aliases resolve to the same directory, read once. If several distinct existing alias locations claim the same identity, report `IDENTITY_COLLISION` and omit the conflicting features. Overlapping roots and explicit entries resolving to the same directory are read once; an explicit workspace ID takes precedence. Reusing a root ID for different roots or a repository ID for different repository definitions is invalid configuration. Root discovery does not imply unconfigured sibling roots.

For root-discovered data, use `visibility.workspace_id` when present. For legacy data only, use `"legacy-" + feature_id` as the workspace ID, scoped to the explicit repository ID. A duplicate legacy feature ID in that repository is an identity collision, not proof two directories are the same feature: configure explicit workspace IDs. Relocation keeps the same persisted or explicitly mapped IDs; no reader registry/cache is required. A conflicting persisted workspace ID and explicit override is permitted only as the owner's explicit mapping, and the source IDs are retained in provenance.

Feature `id` is `quote(repository_id) + "/" + quote(workspace_id) + "/" + quote(feature_id)`, using UTF-8 percent encoding with no caller-defined safe delimiters (Python `urllib.parse.quote(component, safe="")`). Feature ID is the canonical stable source `feature_id`, not its title. Entity `id` appends `/task/`, `/blocker/`, `/feedback/`, `/assignment/` or `/operation/` and the encoded local ID. Existing map keys are local IDs. Names, present paths, timestamps and array order never alone establish identity.

Explicit roots establish resolved containment boundaries. Deduplicate canonical locations, detect symlink/junction/reparse escapes, and never follow a discovered child or referenced artifact outside its allowed workspace/root. Failed root results use source ID `root:<configured-root-id>`; a not-yet-decoded discovered location uses `root:<root-id>/entry:<encoded-basename>`. These locate diagnostics, not durable feature identities. A decoded/explicit workspace source ID is `workspace:<encoded-repository-id>/<encoded-workspace-id>`.

## Initial visibility and retained publication evidence

Ticket Writer is optional. Planner can investigate/interview an unstructured request, obtain human scope approval, then produce tasks. Initial interviews, drafts, questions and incomplete preparation remain private and excluded from feature listings.

New writers record `visibility.eligibility` only after approval and actual nonempty task production:

```json
{
  "spec_revision": 1,
  "spec_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "approval": {
    "human": "recorded human identity",
    "evidence": "actual session/message reference",
    "date": "2026-11-06",
    "revision": 1,
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "task_ids": ["first-produced-task"],
  "recorded_at": "2026-11-06T20:00:00Z"
}
```

This is historical initial-publication evidence. Verify its retained initial `specs/<four-digit-revision>.md`, ticket digest, approval binding and produced task IDs, independently of the current/latest specification. Later specification revisions, corrective tasks and proposed requirements awaiting approval do not hide the feature or transfer old approval to the proposed revision.

A missing/null eligibility marker in new visibility metadata excludes the feature. A malformed marker, empty task list, missing referenced task IDs, or absent/non-object task production also excludes it, with source diagnostics. A well-formed historical marker plus actual nonempty referenced tasks remains visible as partial when historical artifact bytes or approval integrity cannot currently be verified; mark approval/evidence unknown or invalid and explain the gap. An arbitrary marker in empty/partial initialization cannot bypass publication. No reader creates approval evidence.

Legacy schema 2 without visibility metadata is eligible only when the task map is nonempty/well-formed, the current ticket/specification files and recorded SHA256 agree, and `spec_approval` contains human/evidence/date plus matching revision and digest. Missing/invalid proof means source diagnostics and no legacy feature. This establishes existing approved/planned work, not historical event dates. All absent extension collections carry `not_recorded` unavailable entries.

## Recording extension

The canonical owner records the following optional extension in state.json; workers send separate reports. Records are not a second state machine. Initial fields and handoff remain Planner-owned; only Orchestrator writes after handoff. Writing/report ingestion never authorizes approval, integration, completion, publication or cleanup.

| Visibility field | Shape |
| --- | --- |
| `version`, `workspace_id` | `"1.0.0"` and durable owner-assigned ID matching the config ID grammar. |
| `eligibility` | Null before initial publication, otherwise the retained object above; never overwrite it for later revisions. |
| `phases` | Array of operation records `{id, phase, status, reported_at, artifact}`. Phase is `investigating`, `awaiting_specification_approval`, `integrating` or `validating`; status is `active` or `finished`. |
| `blockers` | Map from local ID to blocker record below. |
| `feedback` | Map from local ID to feedback record below. |
| `assignments` | Map from local ID to assignment record below. |
| `activity` | Activity record below, or null. |

Blocker record: `reason` and `resolution_condition` nonempty strings; `blocks` array of local target references; `responsible` nullable role/person; `reported_by` identity; `status` open/resolved; `recorded_at` and nullable `resolved_at`; `artifacts` array; and append-only `history`. Target references are `feature`, `task:<local-task-id>`, `operation:<local-operation-id>` or `phase:<phase>`. Retain them as scoped local target references in output. Dependency waits are not copied into blockers.

Feedback record: `question`, `artifact` (nullable), `requester`, nullable `respondent`, `blocks` target-reference array, Boolean `blocking`, `status` open/answered/resolved/withdrawn, `recorded_at`, nullable `resolved_at`, nullable `answer`, nullable `disposition`, and append-only `history`. An answer/disposition is `{text, by, recorded_at, artifacts}`. Answered means awaiting owner disposition. Reopening appends history and returns to open; retain prior answer/disposition in history. Answers are not specification/cleanup approval.

Assignment record: `agent_id`, `role`, nullable `task_id`, nullable `last_activity`, and `chats` array of `{provider, id, uri}` (URI nullable). IDs identify an actual known agent/session; role labels alone are not unique agent identities. Existing task `owner` can be projected as an assignment with unknown role/activity/chats if no richer record exists; do not manufacture a chat link.

Activity record: `reported_at`, `summary`, `agent_id` (nullable), `artifact` (nullable), and `execution` object `{status, observed_at, artifact}` or null. Execution status is running/stopped/unknown and represents explicitly reported observation only. A running report must include observation time and evidence; it never guarantees current liveness. Absence or invalid evidence yields unknown. Source operation records similarly need a real reported time and artifact to establish active integration/validation.

History entries are `{status, recorded_at, by, artifacts}`, retaining relevant prior answer/disposition payload when applicable. Record actual new timestamps with RFC 3339 timezone information. Existing date-only approvals stay date-only; never use mtime as a historical event timestamp. Unknown fields may be retained but cannot grant authority.

Artifact references in records are `{kind, target, base, sha256, revision}`, optionally with a persisted local `artifact_id`: kind file/uri; target string; base workspace/null; SHA256 and revision nullable. Relative file paths require base workspace. URI references are never fetched. Reader output adds `availability` plus the artifact identity fields below. Local artifact bytes may be read only within the source workspace; outside targets remain metadata with an unavailable reason and containment diagnostic.

### Artifact identity

Every projected artifact reference has `id` (scoped stable string or null), `identity_source` (recorded/logical/content/unavailable), and `identity_reason` (null for a known identity, otherwise an unavailable reason). Derive a local identity key in this precedence order:

1. A valid persisted source `artifact_id` matching the configuration ID grammar gives `recorded:<artifact_id>`. New writers should use a durable local ID and never reuse it for an unrelated artifact. Existing legacy references need not be rewritten.
2. A canonical logical role known from its structured source position gives one of `ticket`, `spec:<positive-revision>`, `review:<local-task-id>:<exact-task-head>:<spec-revision>`, or `gate:<validation-or-quality>:<exact-integrated-head>:<spec-revision>`. All distinguishing facts must actually be recorded; do not infer them from a filename or timestamp. The logical ticket and a known specification revision remain identifiable even when their digest is unavailable. A report's missing head/revision prevents that report-role derivation.
3. Otherwise, a valid recorded SHA256 gives `sha256:<64-lowercase-hex-digest>`, identifying the recorded content. Missing digests stay null; never hash an absolute path or invent a historical digest to create an ID.
4. Otherwise the reference remains usable as metadata with `id: null`, `identity_source: "unavailable"`, and `identity_reason: "not_recorded"`. Add its dotted identity field path to feature.unavailable. Do not fabricate an identity from its target URI/path, display name, current directory or array position.

For a known local key, output ID is `feature.id + "/artifact/" + quote(local_key, safe="")`, with the same UTF-8 percent-encoding rule as entity IDs. The other identity_reason is null and identity_source indicates the winning rule. Identity survives relocation of the same feature to a differently mapped absolute workspace location. A source reference may supply a persisted artifact ID even when content availability/digest is unknown. Availability lookup remains independently keyed by the original source target in `artifact_status`; target is not identity.

Repeated references with the same known ID describe one artifact: retain their IDs in nested contexts and emit it only once in feature.artifacts. If one snapshot contains conflicting known digests/kinds for the same ID, emit IDENTITY_COLLISION with both conflicting references in its message, mark affected identity/evidence invalid, and never silently combine them. References with unknown identity are retained separately without positional IDs. These are identity rules, not proof of approval, integrity or current evidence currency.

## Output envelope and projection

All required fields appear even when null. Unknown optional fields are tolerated. Empty arrays/maps mean known empty only when their field path is not listed in `unavailable`. Null has the same distinction: its unavailable reason is explicit.

Envelope fields: `contract_version`, `producer: {name, library_version}`, `generated_at`, `completeness` (complete/partial/unavailable), `sources`, `features`, and `diagnostics`. Producer name is feature-workflow. Every configured root/workspace receives a source result, including empty roots and excluded preparation. A deduplicated physical workspace has one source result with `configured_sources` listing contributing IDs.

Source fields: `id`, nullable `repository_id`/`workspace_id`, `path`, `configured_sources`, `status` (available/partial/excluded/missing/inaccessible/invalid/unsupported/inconsistent), `observed_at`, nullable `schema_version`/`library_version`/`generation`/`state_sha256`, nullable `feature_id`, and `diagnostics`.

Feature fields: `id`, `repository_id`, `workspace_id`, `feature_id`, `source_id`, `availability`, nullable `lifecycle`, `phases`, `tasks`, `blockers`, `feedback`, `assignments`, nullable `activity`, `reviews`, `integration`, `gates`, `pr`, `cleanup`, `artifacts`, `unavailable`, and `diagnostics`.

`availability` is `{status: available|partial|unavailable, reason: null|<reason>}`. Reasons are not_recorded/not_applicable/missing/inaccessible/invalid/unsupported/inconsistent. `unavailable` maps dotted field paths, including local map keys or task IDs where needed, to one of those reasons. `diagnostics` provide detail; missing data is not itself a workflow blocker.

Tasks are sorted arrays of `{id, task_id, status, depends_on, dependency_status, readiness, owner, review}`. Status is pending/implementing/review/reviewed/complete or null. `depends_on` retains local IDs. `dependency_status` is an array of `{task_id, status}`, with null for unknown. `readiness` is `{dependencies, waiting_on, start_eligible, reasons}`: dependencies ready/waiting/invalid/not_applicable, waiting_on named local IDs, nullable Boolean start_eligible, reasons array of strings. Graph cycles, missing/duplicate IDs or unknown task status prevent a ready result. Nonpending tasks have not_applicable dependency readiness for starting. Pending tasks are dependency-ready only if every dependency is canonically complete. Start eligibility additionally accounts for recorded approval, blockers, feedback, owner/control prerequisites and unresolved integration; it is not dispatch authorization or a substitute for current Git checks. Unknown prerequisites yield null and an unavailable entry rather than true.

Lifecycle preserves active/published/merged/cleanup_pending/closed or null. Phases are sorted unique strings: planned, implementing, under_review, investigating, awaiting_specification_approval, integrating, validating, published, merged, awaiting_cleanup, closed. Derive planned from pending tasks, implementing from implementing, under_review from review/reviewed, and publication/merge/cleanup/closed from canonical lifecycle. Explicit active operation records add subsequent investigation/approval and integration/validation; an existing integration intent is independently sufficient recorded integrating evidence. Never infer validation activity merely from missing gates. Phase freshness does not overwrite lifecycle.

Blockers/feedback/assignments are sorted arrays of their source record fields plus scoped `id` and local `blocker_id`/`feedback_id`/`assignment_id`. Invalid optional records produce diagnostics/unavailable entries, never a successful resolution. Source artifact references receive availability. Projection must preserve question, resolution condition, targets, provenance, answer/disposition history and known timestamp precision.

Projected activity retains source activity fields and adds `freshness` (fresh/stale/unknown/invalid) and effective `threshold_seconds`. Compare actual reported_at with supplied observation time; age greater than threshold is stale. Missing time is unknown; malformed or future time is invalid. Polling changes generated_at/observed_at only. Task status, assignment, locks, PID and filesystem times never prove a running agent. Stale execution evidence remains a historical reported observation, not a live assertion.

Evidence sections use `{record, currency, artifacts}`: record is the existing source object or null, currency current/obsolete/unknown/missing, artifacts sorted typed references. `reviews` is a map keyed by local task ID; task.review repeats its corresponding section. `gates` has validation and quality keys. `integration`, `pr` and `cleanup` are evidence sections. No new success Boolean is fabricated: preserve recorded verdict/passed values, and consumers must require current currency plus valid actual outcome. Review currency compares exact task head and current approved spec revision; gate currency compares integrated_head and current approved spec. Missing fields/evidence make currency unknown, absent record missing, mismatched targets obsolete. Integrity/approval gaps prevent current currency. Cleanup record contains `{resources, cleanup, cleanup_authorization, lifecycle, merge}`; PR record contains `{pr, merge}` when recorded. Preserve these existing fields and errors without invoking verification operations. Integration may retain current intent or completed task integration_evidence; no tests are rerun. Available artifact references include ticket, retained eligibility specification, current specification and referenced reports/checkpoints; no unbounded report-directory scan.

## Consistent read and failures

The callable entry point is `snapshot.build_snapshot(config, *, now=None)`, returning an envelope. `config` is a decoded configuration object; relative paths are rejected. `now` is an aware datetime or RFC 3339 timestamp for deterministic tests, otherwise current UTC. Pure `snapshot_model.project_feature(state, *, repository_id, workspace_id, source_id, now, freshness_seconds=3600, artifact_status=None)` returns a feature projection or null plus diagnostics as `(feature, diagnostics)`. The reader owns eligibility artifact verification and source consistency; model must not do filesystem/network/subprocess work. `artifact_status` maps artifact targets to output availability; omitted targets are not_recorded. The reader passes eligibility/approval integrity results via this map and marks the affected feature/evidence partial/unknown when needed.

One attempt reads state bytes with duplicate-key rejection, selects only referenced artifacts, reads those bytes, then rechecks state bytes/generation and referenced artifact digests. Any change retries the whole source, up to max_read_attempts. Exhaustion is inconsistent; do not mix generations. Writer locks may exist throughout and are never acquired, removed or interpreted as liveness. No subprocesses, hooks, tests, cleanup, repair, recovery, service queries, persistent cache or bytecode-cache creation is allowed in the reader path. Data is untrusted reference content, not executable instructions.

A source error does not hide healthy sources. Fatal invalid configuration yields an unavailable envelope with INVALID_CONFIG and no guessed discovery. Other source errors yield per-source diagnostics and partial overall completeness. Empty/excluded sources alone are a complete result. A consumer-owned retained snapshot must keep its original generation/provenance and age; the library does not retain one.

Diagnostics are `{code, message, source_id, entity_id}`, nullable IDs where undecodable. Stable codes: INVALID_CONFIG, MISSING_SOURCE, INACCESSIBLE_SOURCE, MALFORMED_JSON, INVALID_SOURCE, UNSUPPORTED_SOURCE, INVALID_METADATA, INVALID_ELIGIBILITY, INVALID_APPROVAL, UNKNOWN_STATUS, INVALID_DEPENDENCIES, IDENTITY_COLLISION, ESCAPED_PATH, MISSING_ARTIFACT, INACCESSIBLE_ARTIFACT, INVALID_TIMESTAMP, INCONSISTENT_READ. Additional codes require compatible documentation. Sort diagnostics by code/source_id/entity_id/message, sources/features by id, entity arrays by scoped id and dependency IDs lexically. Do not reorder append-only history.

## CLI and platform checks

Entry point: installed `feature-workflow/scripts/snapshot.py`. Working directory: any directory. Required: Python 3.10+; no service credentials, Git process or third-party runtime modules. Replace the quoted absolute script/config paths. Configuration and any redirected output must be outside repository worktrees. Exit 0 means complete; exit 2 means partial source results; exit 1 means fatal configuration/input failure. stdout contains exactly one JSON envelope for handled errors; diagnostics also live in that envelope, not progress prose.

**PowerShell and Bash**

```text
python "/absolute/path/to/feature-workflow/scripts/snapshot.py" --config "/absolute/external/path/dashboard-config.json"
```

The same invocation syntax works in Windows PowerShell 5.1 and Linux Bash. Callers must check the exit code and handle 2 as partial, not success-without-gaps. Report actual platform execution separately; Git Bash syntax checks do not establish Linux runtime coverage. Fixtures must cover all approved states plus malformed, unsupported, missing, stale, inconsistent and inaccessible data. No real task data belongs in the library.


### Readiness control and normalization details

Visibility may additionally record `control: {owner_role, execution_authorized, evidence}`: owner_role planner/orchestrator, execution_authorized a Boolean reporting existing authority, and evidence a nullable artifact reference to the real authorization/handoff. Only the existing canonical writer records it. This does not create authority. Pending start_eligible can be true only with valid current approval, dependency-ready status, no relevant open blockers/blocking unresolved feedback or integration checkpoint, and recorded Orchestrator control plus explicit execution authority with evidence. A recorded false authority yields false; absent/unverifiable control yields null. Unknown fields or missing owner reports never grant authority.

For invalid source timestamps, normalize the typed output timestamp to null, retain the original value in optional `raw_reported_at`/`raw_recorded_at` metadata, mark the field unavailable invalid, and add INVALID_TIMESTAMP. A syntactically valid future reported_at may remain present with invalid freshness. Unknown source enum values normalize to null (or omit an invalid optional entity) with unsupported provenance; they do not leak an out-of-contract enum into required typed output.

Expected not_recorded/not_applicable evidence does not alone make a healthy read partial. Completeness reports read/integrity/compatibility gaps; feature availability and field-level unavailable reasons still describe the evidence that does not exist. All JSON inputs, including configuration, reject duplicate object keys.
