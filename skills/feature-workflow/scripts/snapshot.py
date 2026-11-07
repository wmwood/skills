"""Read-only, bounded local workflow snapshots; no workflow mutation helpers."""
import sys

# CLI dependencies must not cache bytecode. Callable consumers disable caching
# before loading this module; a default CPython importer caches before execution.
sys.dont_write_bytecode = True

import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
from urllib.parse import quote

_model_spec = importlib.util.spec_from_file_location(
    "_workflow_snapshot_model", Path(__file__).with_name("snapshot_model.py"))
_model = importlib.util.module_from_spec(_model_spec)
_model_spec.loader.exec_module(_model)

_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_VERSION = re.compile(r"1\.[0-9]+\.[0-9]+\Z")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z")


def _diag(code, message, source_id=None, entity_id=None):
    return dict(code=code, message=message, source_id=source_id, entity_id=entity_id)


def _diag_key(value):
    return tuple(value.get(k) or "" for k in ("code", "source_id", "entity_id", "message"))


def _clock(value):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str) and _TIME.fullmatch(value):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be an aware datetime or RFC 3339 timestamp")
    return value.astimezone(timezone.utc)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON constant: " + value)


def _number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number: " + value)
    return number


def _json(data):
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs,
                      parse_constant=_constant, parse_float=_number)


def _key(path):
    try:
        return os.path.normcase(str(path.resolve()))
    except (OSError, RuntimeError):
        return os.path.normcase(os.path.abspath(path))


def _inside(path, parent):
    return path.resolve().is_relative_to(parent.resolve())


def _linked(path):
    """Check lexical components without reading a linked target's file bytes."""
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if part.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            return True
    return False


def _external(path, repositories):
    if any(_inside(path, repo) for repo in repositories):
        raise ValueError("Private workflow location is inside a configured repository")
    for parent in (path, *path.parents):
        if os.path.lexists(parent / ".git"):
            raise ValueError("Private workflow location is inside a Git worktree")


def _path(value):
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("Paths must be nonempty absolute host-native strings")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("Paths must be absolute host-native paths")
    return path


def _identifier(value):
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        raise ValueError("Invalid stable configuration identity")
    return value


def _configuration(config):
    if not isinstance(config, dict) or not isinstance(config.get("config_version"), str) or not _VERSION.fullmatch(config["config_version"]):
        raise ValueError("Unsupported or missing configuration version")
    rows = config.get("repositories")
    if not isinstance(rows, list) or not rows:
        raise ValueError("At least one configured repository is required")
    repositories = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Repository definitions must be objects")
        key, path = _identifier(row.get("id")), _path(row.get("path"))
        if key in repositories and _key(repositories[key]) != _key(path):
            raise ValueError("Repository identity has conflicting locations")
        repositories[key] = path
    locations = {}
    for field in ("workspace_roots", "workspaces"):
        rows = config.get(field, [])
        if not isinstance(rows, list):
            raise ValueError(field + " must be an array")
        result = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Workspace definitions must be objects")
            key = _identifier(row.get("id"))
            repository_id = _identifier(row.get("repository_id"))
            if repository_id not in repositories:
                raise ValueError("Workspace references an unknown repository")
            result.append(dict(id=key, repository_id=repository_id, path=_path(row.get("path"))))
        locations[field] = result
    if not any(locations.values()):
        raise ValueError("Configure an explicit root or workspace")
    roots = {}
    for row in locations["workspace_roots"]:
        value = (row["repository_id"], _key(row["path"]))
        if row["id"] in roots and roots[row["id"]] != value:
            raise ValueError("Root identity has conflicting definitions")
        roots[row["id"]] = value
    for name, default, maximum in (("freshness_seconds", 3600, None), ("max_read_attempts", 3, 3)):
        value = config.get(name, default)
        if type(value) is not int or value < 1 or maximum is not None and value > maximum:
            raise ValueError("Invalid " + name)
        locations[name] = value
    return repositories, locations


def _source(identity, path, configured, observed, repository=None, workspace=None):
    return dict(id=identity, repository_id=repository, workspace_id=workspace,
                path=str(path), configured_sources=sorted(set(configured)),
                status="available", observed_at=observed, schema_version=None,
                library_version=None, generation=None, state_sha256=None,
                feature_id=None, diagnostics=[])


def _fail(source, status, code, message):
    source["status"] = status
    source["diagnostics"].append(_diag(code, message, source["id"]))
    return source


def _observe(path, boundary):
    """A comparable observation, including absence and failed reads."""
    try:
        if _linked(path) or not _inside(path, boundary):
            return ("unavailable", "invalid", "escaped"), None
        if not stat.S_ISREG(path.stat().st_mode):
            return ("unavailable", "invalid", "not_file"), None
        data = path.read_bytes()
        return ("available", hashlib.sha256(data).hexdigest(), _key(path)), data
    except FileNotFoundError:
        return ("unavailable", "missing", None), None
    except PermissionError as error:
        return ("unavailable", "inaccessible", error.errno), None
    except OSError as error:
        return ("unavailable", "invalid", error.errno), None
    except (ValueError, RuntimeError):
        return ("unavailable", "invalid", "escaped"), None


def _references(state, *, optional=True):
    """Select explicit references and canonical approval artifacts, never scan reports."""
    result = defaultdict(list)
    if not isinstance(state, dict):
        return result
    result["ticket.md"].append(dict(kind="file", target="ticket.md", base="workspace",
                                   sha256=state.get("ticket_sha256"), required_digest=True))
    revisions = [(state.get("spec_revision"), state.get("spec_sha256"))]
    visibility = state.get("visibility")
    marker = visibility.get("eligibility") if isinstance(visibility, dict) else None
    if isinstance(marker, dict):
        revisions.append((marker.get("spec_revision"), marker.get("spec_sha256")))
    for revision, digest in revisions:
        if type(revision) is int and revision > 0:
            target = "specs/%04d.md" % revision
            result[target].append(dict(kind="file", target=target, base="workspace",
                                       sha256=digest, required_digest=True))

    if not optional:
        return result

    def walk(value):
        if isinstance(value, dict):
            if value.get("kind") in ("file", "uri") and isinstance(value.get("target"), str):
                result[value["target"]].append(value)
                return
            for key, child in value.items():
                if key == "report" and isinstance(child, str):
                    result[child].append(dict(kind="file", target=child, base="workspace", sha256=None))
                else:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    for key in ("visibility", "tasks", "gates", "integration", "pr", "merge", "cleanup", "cleanup_authorization"):
        walk(state.get(key))
    return result


def _artifact_observations(workspace, references, source_id):
    availability, observations, diagnostics = {}, {}, []
    for target, refs in sorted(references.items()):
        if not target or "\0" in target:
            availability[target] = dict(status="unavailable", reason="invalid")
            diagnostics.append(_diag("INVALID_METADATA", "Invalid artifact target", source_id))
            continue
        kinds = {r.get("kind") for r in refs}
        if kinds == {"uri"}:
            availability[target] = dict(status="unavailable", reason="not_recorded")
            continue
        if kinds != {"file"}:
            availability[target] = dict(status="unavailable", reason="invalid")
            diagnostics.append(_diag("INVALID_METADATA", "Conflicting artifact kinds: " + target, source_id))
            continue
        raw = Path(target)
        valid_base = all(r.get("base") in (None, "workspace") and
                         (raw.is_absolute() or r.get("base") == "workspace") for r in refs)
        path = raw if raw.is_absolute() else workspace / raw
        if not valid_base:
            availability[target] = dict(status="unavailable", reason="invalid")
            diagnostics.append(_diag("INVALID_METADATA", "Invalid artifact base: " + target, source_id))
            continue
        observation, data = _observe(path, workspace)
        observations[target] = (path, observation)
        if observation[0] != "available":
            reason = observation[1]
            code = ("ESCAPED_PATH" if observation[2] == "escaped" else
                    "MISSING_ARTIFACT" if reason == "missing" else
                    "INACCESSIBLE_ARTIFACT" if reason == "inaccessible" else "INVALID_METADATA")
            diagnostics.append(_diag(code, "Artifact unavailable: " + target, source_id))
            availability[target] = dict(status="unavailable", reason=reason)
            continue
        recorded = [r.get("sha256") for r in refs]
        bad = any(v is not None and (not isinstance(v, str) or not _DIGEST.fullmatch(v)) for v in recorded)
        bad = bad or any(r.get("required_digest") and not isinstance(r.get("sha256"), str) for r in refs)
        digests = {v for v in recorded if isinstance(v, str) and _DIGEST.fullmatch(v)}
        if bad or len(digests) > 1 or digests and observation[1] not in digests:
            availability[target] = dict(status="unavailable", reason="invalid")
            diagnostics.append(_diag("INVALID_METADATA", "Artifact digest mismatch or invalid digest: " + target, source_id))
        else:
            availability[target] = dict(status="available", reason=None)
    return availability, observations, diagnostics


def _preparation(state):
    if not isinstance(state, dict) or type(state.get("schema_version")) is not int or state["schema_version"] != 2:
        return False
    if not isinstance(state.get("library_version"), str) or not _VERSION.fullmatch(state["library_version"]):
        return False
    visibility = state.get("visibility")
    if isinstance(visibility, dict) and isinstance(visibility.get("version"), str) and _VERSION.fullmatch(visibility["version"]):
        return visibility.get("eligibility") is None
    return visibility is None and state.get("tasks") == {}


def _supported(state):
    return (isinstance(state, dict) and type(state.get("schema_version")) is int and state["schema_version"] == 2
            and isinstance(state.get("library_version"), str) and _VERSION.fullmatch(state["library_version"])
            and (state.get("visibility") is None or isinstance(state["visibility"], dict)
                 and isinstance(state["visibility"].get("version"), str)
                 and _VERSION.fullmatch(state["visibility"]["version"])))


def _source_fields(source, state):
    if not isinstance(state, dict):
        return
    for field in ("schema_version", "generation"):
        value = state.get(field)
        valid = type(value) is int and value >= 0
        source[field] = value if valid else None
        if value is not None and not valid:
            source["diagnostics"].append(_diag("INVALID_SOURCE",
                "Invalid typed source field: " + field, source["id"]))
    value = state.get("library_version")
    valid = isinstance(value, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value)
    source["library_version"] = value if valid else None
    if value is not None and not valid:
        source["diagnostics"].append(_diag("INVALID_SOURCE",
            "Invalid typed source field: library_version", source["id"]))
    value = state.get("feature_id")
    if value is not None and (not isinstance(value, str) or not value.strip()):
        source["diagnostics"].append(_diag("INVALID_SOURCE",
            "Invalid typed source field: feature_id", source["id"]))
    # feature_id remains private until an eligible feature is actually projected.


def _initial_publication(state):
    """Return a privacy gate without walking optional draft metadata."""
    if not _supported(state):
        return "invalid", None
    if _preparation(state):
        return "preparation", None
    tasks = state.get("tasks")
    if (not isinstance(tasks, dict) or not tasks or not all(
            isinstance(k, str) and k.strip() and isinstance(v, dict)
            for k, v in tasks.items())):
        return "invalid", ("INVALID_ELIGIBILITY", "Nonempty produced task records are required")
    visibility = state.get("visibility")
    if visibility is None:
        revision, digest = state.get("spec_revision"), state.get("spec_sha256")
        approval = state.get("spec_approval")
        valid = (type(revision) is int and revision > 0 and isinstance(digest, str)
                 and _DIGEST.fullmatch(digest) and isinstance(approval, dict)
                 and all(isinstance(approval.get(k), str) and approval[k].strip()
                         for k in ("human", "evidence", "date"))
                 and type(approval.get("revision")) is int and approval["revision"] == revision
                 and approval.get("sha256") == digest
                 and isinstance(state.get("ticket_sha256"), str)
                 and _DIGEST.fullmatch(state["ticket_sha256"]))
        if valid:
            try:
                valid = date.fromisoformat(approval["date"]).isoformat() == approval["date"]
            except ValueError:
                valid = False
        return ("legacy", None) if valid else (
            "invalid", ("INVALID_APPROVAL", "Legacy initial approval proof is invalid or unavailable"))
    marker = visibility.get("eligibility")
    if not isinstance(marker, dict):
        return "invalid", ("INVALID_ELIGIBILITY", "Initial eligibility marker is malformed")
    revision, digest = marker.get("spec_revision"), marker.get("spec_sha256")
    approval, task_ids = marker.get("approval"), marker.get("task_ids")
    valid = (type(revision) is int and revision > 0 and isinstance(digest, str)
             and _DIGEST.fullmatch(digest) and isinstance(approval, dict)
             and all(isinstance(approval.get(k), str) and approval[k].strip()
                     for k in ("human", "evidence", "date"))
             and type(approval.get("revision")) is int and approval["revision"] > 0
             and isinstance(approval.get("sha256"), str) and _DIGEST.fullmatch(approval["sha256"])
             and isinstance(task_ids, list) and task_ids
             and all(isinstance(k, str) and k.strip() for k in task_ids)
             and len(set(task_ids)) == len(task_ids) and all(k in tasks for k in task_ids)
             and isinstance(marker.get("recorded_at"), str)
             and _TIME.fullmatch(marker["recorded_at"]))
    if valid:
        try:
            _clock(marker["recorded_at"])
        except (ValueError, OverflowError):
            valid = False
    return ("historical", None) if valid else (
        "invalid", ("INVALID_ELIGIBILITY", "Initial eligibility must bind retained proof and produced tasks"))


def _read_workspace(path, configured, repository_id, explicit_id, provisional_id,
                    repositories, now, attempts, freshness):
    observed = now.isoformat().replace("+00:00", "Z")
    source = _source(provisional_id, path, configured, observed, repository_id, explicit_id)
    try:
        _external(path, repositories.values())
        if _linked(path):
            return _fail(source, "invalid", "ESCAPED_PATH", "Workspace is a linked/reparse location"), None
    except (ValueError, OSError, RuntimeError) as error:
        return _fail(source, "invalid", "ESCAPED_PATH", str(error)), None
    state_path = path / "state.json"
    for unused in range(attempts):
        first, raw = _observe(state_path, path)
        state, parse_error = None, None
        if raw is not None:
            try:
                state = _json(raw)
            except (ValueError, UnicodeError, RecursionError):
                parse_error = "State JSON is malformed or contains duplicate/non-finite values"
        publication, publication_error = _initial_publication(state)
        refs = _references(state, optional=False) if publication in ("legacy", "historical") else {}
        statuses, initial_artifacts, errors = _artifact_observations(path, refs, source["id"])
        artifacts = list(initial_artifacts.values())
        canonical_verified = bool(refs) and all(v["status"] == "available" for v in statuses.values())
        if publication == "historical" or publication == "legacy" and canonical_verified:
            try:
                refs = _references(state)
            except RecursionError:
                refs, parse_error = {}, "Referenced metadata exceeds supported nesting"
            full_statuses, full_artifacts, full_errors = _artifact_observations(path, refs, source["id"])
            statuses.update(full_statuses)
            artifacts.extend(full_artifacts.values())
            errors.extend(full_errors)
        last, unused_raw = _observe(state_path, path)
        stable = first == last
        for artifact_path, observation in artifacts:
            stable = stable and _observe(artifact_path, path)[0] == observation
        if not stable:
            continue
        if raw is None:
            reason = first[1]
            return _fail(source, "missing" if reason == "missing" else "inaccessible" if reason == "inaccessible" else "invalid",
                         "MISSING_SOURCE" if reason == "missing" else "INACCESSIBLE_SOURCE" if reason == "inaccessible" else "ESCAPED_PATH" if first[2] == "escaped" else "INVALID_SOURCE",
                         "Cannot read state.json"), None
        source["state_sha256"] = hashlib.sha256(raw).hexdigest()
        if parse_error is not None:
            return _fail(source, "invalid", "MALFORMED_JSON", parse_error), None
        _source_fields(source, state)
        if publication == "preparation":
            source["status"] = "partial" if source["diagnostics"] else "excluded"
            return source, None
        if not isinstance(state, dict):
            return _fail(source, "invalid", "INVALID_SOURCE", "State must be an object"), None
        if type(state.get("schema_version")) is not int or state["schema_version"] != 2 or not isinstance(state.get("library_version"), str) or not _VERSION.fullmatch(state["library_version"]):
            return _fail(source, "unsupported", "UNSUPPORTED_SOURCE", "Unsupported state schema or library version"), None
        visibility = state.get("visibility")
        if visibility is not None and not isinstance(visibility, dict):
            return _fail(source, "invalid", "INVALID_METADATA", "Visibility metadata must be an object"), None
        if visibility is not None and (not isinstance(visibility.get("version"), str) or not _VERSION.fullmatch(visibility["version"])):
            return _fail(source, "unsupported", "UNSUPPORTED_SOURCE", "Unsupported visibility version"), None
        if not isinstance(state.get("feature_id"), str) or not state["feature_id"].strip():
            return _fail(source, "invalid", "INVALID_SOURCE", "Missing canonical feature identity"), None
        if publication_error:
            return _fail(source, "invalid", *publication_error), None
        if publication == "legacy" and not canonical_verified:
            source["diagnostics"].extend(errors)
            return _fail(source, "invalid", "INVALID_APPROVAL",
                         "Legacy approval artifacts cannot currently be verified"), None
        workspace_id = explicit_id
        if workspace_id is None and isinstance(state, dict):
            visibility = state.get("visibility")
            workspace_id = visibility.get("workspace_id") if isinstance(visibility, dict) else (
                "legacy-" + state["feature_id"] if isinstance(state.get("feature_id"), str) else None)
        if not isinstance(workspace_id, str) or not _IDENT.fullmatch(workspace_id):
            # Unsupported data still gets a source result rather than an invented identity.
            return _fail(source, "unsupported" if not _supported(state) else "invalid",
                         "UNSUPPORTED_SOURCE" if not _supported(state) else "INVALID_METADATA",
                         "No usable workspace identity in source; configure an explicit mapping"), None
        source["workspace_id"] = workspace_id
        source["id"] = "workspace:" + quote(repository_id, safe="") + "/" + quote(workspace_id, safe="")
        for error in errors:
            error["source_id"] = source["id"]
        try:
            feature, model_errors = _model.project_feature(
                state, repository_id=repository_id, workspace_id=workspace_id,
                source_id=source["id"], now=now, freshness_seconds=freshness, artifact_status=statuses)
        except (ValueError, TypeError, RecursionError, OverflowError) as error:
            return _fail(source, "invalid", "INVALID_SOURCE", "Source cannot be projected safely"), None
        combined = source["diagnostics"] + errors + model_errors
        for error in combined:
            error["source_id"] = source["id"]
        source["diagnostics"] = sorted({_diag_key(d): d for d in combined}.values(), key=_diag_key)
        if feature is None:
            codes = {e["code"] for e in source["diagnostics"]}
            source["status"] = "unsupported" if "UNSUPPORTED_SOURCE" in codes else "invalid" if codes else "excluded"
        else:
            source["feature_id"] = state["feature_id"]
            if isinstance(visibility, dict) and isinstance(visibility.get("workspace_id"), str):
                source["recorded_workspace_id"] = visibility["workspace_id"]
            source["status"] = "partial" if source["diagnostics"] or feature["availability"]["status"] != "available" else "available"
            if errors:
                feature["availability"] = dict(status="partial", reason=next(
                    (v["reason"] for v in statuses.values() if v["reason"] not in (None, "not_recorded", "not_applicable")), "invalid"))
        return source, feature
    return _fail(source, "inconsistent", "INCONSISTENT_READ",
                 "State or referenced artifacts changed during all bounded read attempts"), None


def _envelope(now):
    return dict(contract_version="1.0.0", producer=dict(name="feature-workflow", library_version="1.1.0"),
                generated_at=now.isoformat().replace("+00:00", "Z"),
                completeness="complete", sources=[], features=[], diagnostics=[])


def _invalid(message, now=None):
    envelope = _envelope(now or datetime.now(timezone.utc))
    envelope.update(completeness="unavailable", diagnostics=[_diag("INVALID_CONFIG", message)])
    return envelope


def build_snapshot(config, *, now=None):
    """Return JSON-compatible recorded status without writing or invoking services."""
    try:
        observed = _clock(now)
        repositories, options = _configuration(config)
    except (ValueError, OSError, TypeError, RuntimeError, OverflowError) as error:
        return _invalid(str(error))
    envelope = _envelope(observed)
    candidates = {}
    blocked = set()

    def candidate(path, repository, identity, configured):
        key = _key(path)
        value = candidates.setdefault(key, dict(path=path, repositories=set(), identities=set(), configured=set()))
        value["repositories"].add(repository)
        if identity is not None:
            value["identities"].add(identity)
        value["configured"].add(configured)
        return value

    aliases = defaultdict(list)
    for row in options["workspaces"]:
        aliases[(row["repository_id"], row["id"])].append(row["path"])
    for (repository, identity), paths in sorted(aliases.items()):
        distinct = {_key(p): p for p in paths}
        existing = {key: p for key, p in distinct.items() if os.path.lexists(p)}
        configured = "workspace:" + quote(repository, safe="") + "/" + quote(identity, safe="")
        if len(existing) > 1:
            blocked.update(existing)
            source = _source(configured, sorted(existing.values(), key=str)[0], [configured],
                             envelope["generated_at"], repository, identity)
            source["alias_paths"] = sorted(str(p) for p in distinct.values())
            envelope["sources"].append(_fail(source, "invalid", "IDENTITY_COLLISION",
                                              "Several existing alias locations claim one workspace identity"))
        else:
            path = next(iter(existing.values())) if existing else sorted(distinct.values(), key=str)[0]
            value = candidate(path, repository, identity, configured)
            value["alias_paths"] = sorted(str(p) for p in distinct.values())

    seen_roots = set()
    for row in options["workspace_roots"]:
        root, root_id = row["path"], "root:" + row["id"]
        if root_id in seen_roots:
            continue
        seen_roots.add(root_id)
        source = _source(root_id, root, [root_id], envelope["generated_at"], row["repository_id"])
        envelope["sources"].append(source)
        try:
            _external(root, repositories.values())
            if _linked(root):
                _fail(source, "invalid", "ESCAPED_PATH", "Root is a linked/reparse location")
                continue
            for child in sorted(root.iterdir(), key=lambda p: p.name):
                provisional = root_id + "/entry:" + quote(child.name, safe="")
                if _linked(child):
                    entry = _source(provisional, child, [root_id], envelope["generated_at"], row["repository_id"])
                    envelope["sources"].append(_fail(entry, "invalid", "ESCAPED_PATH", "Discovered linked/reparse entry"))
                    continue
                if child.is_dir() and os.path.lexists(child / "state.json"):
                    candidate(child, row["repository_id"], None, root_id)
        except FileNotFoundError:
            _fail(source, "missing", "MISSING_SOURCE", "Configured root does not exist")
        except PermissionError:
            _fail(source, "inaccessible", "INACCESSIBLE_SOURCE", "Configured root is inaccessible")
        except (ValueError, OSError, RuntimeError) as error:
            _fail(source, "invalid", "ESCAPED_PATH" if isinstance(error, ValueError) else "INVALID_SOURCE", str(error))

    for key, value in sorted(candidates.items()):
        if key in blocked:
            continue
        identities, repos = value["identities"], value["repositories"]
        explicit = sorted(identities)[0] if identities else None
        repository = sorted(repos)[0]
        provisional = ("workspace:" + quote(repository, safe="") + "/" + quote(explicit, safe="") if explicit
                       else sorted(value["configured"])[0] + "/entry:" + quote(value["path"].name, safe=""))
        if len(identities) > 1 or len(repos) > 1:
            source = _source(provisional, value["path"], value["configured"], envelope["generated_at"])
            envelope["sources"].append(_fail(source, "invalid", "IDENTITY_COLLISION",
                                              "One physical workspace has conflicting explicit identities/repositories"))
            continue
        source, feature = _read_workspace(value["path"], value["configured"], repository, explicit,
                                          provisional, repositories, observed,
                                          options["max_read_attempts"], options["freshness_seconds"])
        if "alias_paths" in value:
            source["alias_paths"] = value["alias_paths"]
        envelope["sources"].append(source)
        if feature is not None:
            envelope["features"].append(feature)

    # Root-discovered persisted IDs and legacy IDs can collide across real directories.
    grouped = defaultdict(list)
    for source in envelope["sources"]:
        grouped[source["id"]].append(source)
    collisions = {key for key, values in grouped.items() if len(values) > 1}
    if collisions:
        consolidated = []
        for key, sources in grouped.items():
            first = sources[0]
            if key in collisions:
                first["alias_paths"] = sorted({s["path"] for s in sources})
                first["configured_sources"] = sorted({v for s in sources for v in s["configured_sources"]})
                _fail(first, "invalid", "IDENTITY_COLLISION", "Distinct workspaces claim identity " + key)
            consolidated.append(first)
        envelope["sources"] = consolidated
        envelope["features"] = [f for f in envelope["features"] if f["source_id"] not in collisions]
    envelope["sources"].sort(key=lambda s: s["id"])
    envelope["features"].sort(key=lambda f: f["id"])
    envelope["diagnostics"] = sorted([d for s in envelope["sources"] for d in s["diagnostics"]], key=_diag_key)
    if any(s["status"] not in ("available", "excluded") for s in envelope["sources"]):
        envelope["completeness"] = "partial"
    return envelope


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("--config", required=True)
        args = parser.parse_args(argv)
        path = _path(args.config)
        _external(path, [])
        if _linked(path):
            raise ValueError("Configuration must not be a linked/reparse location")
        config = _json(path.read_bytes())
        repositories, unused = _configuration(config)
        _external(path, repositories.values())
        result = build_snapshot(config)
    except (ValueError, UnicodeError, OSError, RecursionError, RuntimeError) as error:
        result = _invalid(str(error))
    print(json.dumps(result, ensure_ascii=True, allow_nan=False, sort_keys=True))
    return {"complete": 0, "partial": 2, "unavailable": 1}[result["completeness"]]


if __name__ == "__main__":
    raise SystemExit(main())
