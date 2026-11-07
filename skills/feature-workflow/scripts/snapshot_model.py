"""Pure projection of recorded workflow evidence into snapshot contract 1.x.

The caller supplies artifact availability after its own consistent, read-only
verification. This module neither reads files nor verifies remote resources.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
import re
import hashlib
import json
from urllib.parse import quote, urlparse

_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)\Z")
_TASK_STATES = {"pending", "implementing", "review", "reviewed", "complete"}
_LIFECYCLES = {"active", "published", "merged", "cleanup_pending", "closed"}
_REASONS = {"not_recorded", "not_applicable", "missing", "inaccessible",
            "invalid", "unsupported", "inconsistent"}
_GAPS = _REASONS - {"not_recorded", "not_applicable"}


def _member(value, choices):
    return isinstance(value, str) and value in choices


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _positive(value):
    return type(value) is int and value > 0


def _digest(value):
    return isinstance(value, str) and bool(_DIGEST.fullmatch(value))


def _time(value):
    if not isinstance(value, str) or not _TIME.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _now(value):
    parsed = _time(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("now must be an aware datetime or RFC 3339 timestamp")
    return parsed.astimezone(timezone.utc)


def _approval(value, revision, digest):
    if not isinstance(value, dict) or not _positive(revision) or not _digest(digest):
        return False
    if not all(_text(value.get(k)) for k in ("human", "evidence", "date")):
        return False
    try:
        valid_date = date.fromisoformat(value["date"]).isoformat() == value["date"]
    except (TypeError, ValueError):
        valid_date = False
    return (valid_date and value.get("revision") == revision
            and type(value.get("revision")) is int and value.get("sha256") == digest)


def _diagnostic_key(item):
    return tuple(item.get(k) or "" for k in ("code", "source_id", "entity_id", "message"))


class _Projection:
    def __init__(self, state, repository_id, workspace_id, source_id, now, threshold, artifacts):
        self.state = state
        self.source_id = source_id
        self.now = now
        self.threshold = threshold
        self.artifact_status = artifacts
        self.id = "/".join(quote(v, safe="") for v in
                           (repository_id, workspace_id, state["feature_id"]))
        self.unavailable = {}
        self.diagnostics = []
        self.artifacts = []
        self.known_artifacts = {}
        self.collision_ids = set()
        self.partial = False
        self.unknown_prerequisites = []

    def diag(self, code, message, entity=None):
        self.diagnostics.append(dict(code=code, message=message,
                                     source_id=self.source_id, entity_id=entity or self.id))
        self.partial = True

    def absent(self, path, reason="not_recorded"):
        self.unavailable[path] = reason
        if reason in _GAPS:
            self.partial = True

    def timestamp(self, value, path, output, key):
        if value is None:
            output[key] = None
            self.absent(path)
        elif _time(value) is None:
            output[key] = None
            output["raw_" + key] = deepcopy(value)
            self.absent(path, "invalid")
            self.diag("INVALID_TIMESTAMP", "Invalid timestamp at " + path)
        else:
            output[key] = value

    def availability(self, target):
        value = self.artifact_status.get(target)
        if (isinstance(value, dict) and _member(value.get("status"),
                {"available", "partial", "unavailable"})):
            reason = value.get("reason")
            if ((value["status"] == "available" and reason is None)
                    or (value["status"] != "available" and _member(reason, _REASONS))):
                return deepcopy(value)
        if value is None:
            return dict(status="unavailable", reason="not_recorded")
        return dict(status="unavailable", reason="invalid")

    def artifact(self, ref, path, logical=None):
        if ref is None:
            self.absent(path)
            return None
        if (not isinstance(ref, dict) or not _member(ref.get("kind"), {"file", "uri"})
                or not _text(ref.get("target")) or (ref.get("base") is not None and ref.get("base") != "workspace")):
            self.absent(path, "invalid")
            self.diag("INVALID_METADATA", "Invalid artifact reference at " + path)
            return None
        absolute_file = (ref["target"].startswith(("/", "\\\\"))
                         or re.match(r"^[A-Za-z]:[\\/]", ref["target"]))
        if ref["kind"] == "file" and not absolute_file and ref.get("base") != "workspace":
            self.absent(path, "invalid")
            self.diag("INVALID_METADATA", "Relative file artifact requires workspace base at " + path)
            return None
        out = deepcopy(ref)
        out.update(kind=ref["kind"], target=ref["target"], base=ref.get("base"),
                   sha256=ref.get("sha256") if _digest(ref.get("sha256")) else None,
                   revision=ref.get("revision") if _positive(ref.get("revision")) else None,
                   availability=self.availability(ref["target"]))
        if out["sha256"] is None:
            self.absent(path + ".sha256")
        if out["revision"] is None:
            self.absent(path + ".revision", "not_applicable" if logical == "ticket" else "not_recorded")
        if ref.get("sha256") is not None and not _digest(ref["sha256"]):
            self.absent(path + ".sha256", "invalid")
            self.diag("INVALID_METADATA", "Invalid recorded digest at " + path)
        local = None
        persisted = ref.get("artifact_id")
        if isinstance(persisted, str) and _IDENT.fullmatch(persisted):
            local, origin = "recorded:" + persisted, "recorded"
        elif logical:
            local, origin = logical, "logical"
        elif out["sha256"]:
            local, origin = "sha256:" + out["sha256"], "content"
        else:
            origin = "unavailable"
        out.update(id=self.id + "/artifact/" + quote(local, safe="") if local else None,
                   identity_source=origin,
                   identity_reason=None if local else "not_recorded")
        if not local:
            self.absent(path + ".id")
        if out["availability"]["reason"] in _GAPS:
            self.absent(path, out["availability"]["reason"])
        if out["id"] in self.known_artifacts:
            previous = self.known_artifacts[out["id"]]
            conflict = (previous["kind"] != out["kind"]
                        or (previous["sha256"] and out["sha256"]
                            and previous["sha256"] != out["sha256"]))
            if conflict:
                self.collision_ids.add(out["id"])
                self.diag("IDENTITY_COLLISION",
                          "Conflicting artifact references: " + repr(previous) + " / " + repr(out))
                for item in self.artifacts:
                    if item["id"] == out["id"]:
                        item.update(id=None, identity_source="unavailable", identity_reason="invalid")
                out.update(id=None, identity_source="unavailable", identity_reason="invalid")
                self.absent(path + ".id", "invalid")
            elif previous["sha256"] is None and out["sha256"]:
                previous["sha256"] = out["sha256"]
        elif out["id"]:
            self.known_artifacts[out["id"]] = out
            self.artifacts.append(out)
        else:
            self.artifacts.append(out)
        return out

    def artifact_list(self, refs, path):
        if refs is None:
            self.absent(path)
            return []
        if not isinstance(refs, list):
            self.absent(path, "invalid")
            self.diag("INVALID_METADATA", "Expected artifact array at " + path)
            return []
        result = [self.artifact(ref, path + "." + str(i)) for i, ref in enumerate(refs)]
        return sorted((v for v in result if v is not None),
                      key=lambda a: (a["id"] or "", a["target"]))

    def canonical_artifact(self, target, digest, revision=None, logical=None):
        return self.artifact(dict(kind="file", target=target, base="workspace",
                                  sha256=digest, revision=revision), "artifacts." + target, logical)

    def verified(self, target):
        return self.availability(target)["status"] == "available"

    def eligibility(self):
        tasks = self.state.get("tasks")
        if not isinstance(tasks, dict) or not tasks or not all(
                _text(k) and isinstance(v, dict) for k, v in tasks.items()):
            self.diag("INVALID_ELIGIBILITY", "Nonempty produced task records are required")
            return False
        visibility = self.state.get("visibility")
        ticket = self.canonical_artifact("ticket.md", self.state.get("ticket_sha256"), logical="ticket")
        rev = self.state.get("spec_revision")
        current_target = "specs/%04d.md" % rev if _positive(rev) else None
        if current_target:
            self.canonical_artifact(current_target, self.state.get("spec_sha256"), rev, "spec:" + str(rev))
        current = (_approval(self.state.get("spec_approval"), rev, self.state.get("spec_sha256"))
                   and _digest(self.state.get("ticket_sha256")) and self.verified("ticket.md")
                   and current_target is not None and self.verified(current_target))
        self.current_approval = bool(current)
        if visibility is None:
            if not current:
                self.diag("INVALID_APPROVAL", "Legacy feature lacks verified current ticket/specification approval")
                return False
            return True
        marker = visibility.get("eligibility")
        if marker is None:
            return False
        if not isinstance(marker, dict):
            self.diag("INVALID_ELIGIBILITY", "Malformed initial eligibility marker")
            return False
        initial_rev, initial_sha = marker.get("spec_revision"), marker.get("spec_sha256")
        task_ids = marker.get("task_ids")
        shape = (_positive(initial_rev) and _digest(initial_sha) and isinstance(marker.get("approval"), dict)
                 and all(_text(marker["approval"].get(k)) for k in ("human", "evidence", "date"))
                 and _positive(marker["approval"].get("revision")) and _digest(marker["approval"].get("sha256"))
                 and isinstance(task_ids, list) and task_ids and all(_text(k) for k in task_ids)
                 and len(set(task_ids)) == len(task_ids) and all(k in tasks for k in task_ids)
                 and _time(marker.get("recorded_at")) is not None)
        if not shape:
            self.diag("INVALID_ELIGIBILITY", "Eligibility must identify produced tasks and retained initial approval")
            return False
        target = "specs/%04d.md" % initial_rev
        self.canonical_artifact(target, initial_sha, initial_rev, "spec:" + str(initial_rev))
        initial_ok = (_approval(marker["approval"], initial_rev, initial_sha)
                      and _digest(self.state.get("ticket_sha256"))
                      and ticket["availability"]["status"] == "available" and self.verified(target))
        if not initial_ok:
            self.absent("eligibility", "invalid" if not _approval(marker["approval"], initial_rev, initial_sha)
                        else self.availability(target).get("reason") or "invalid")
            self.diag("INVALID_APPROVAL", "Retained initial eligibility proof cannot currently be verified")
        if not current:
            self.absent("approval", "invalid")
            self.diag("INVALID_APPROVAL", "Current specification approval/integrity cannot be verified")
        return True

    def activity(self, value, path):
        if value is None:
            self.absent(path)
            return None
        if not isinstance(value, dict):
            self.absent(path, "invalid")
            self.diag("INVALID_METADATA", "Invalid activity at " + path)
            return None
        out = deepcopy(value)
        out.update(summary=value.get("summary") if isinstance(value.get("summary"), str) else None,
                   agent_id=value.get("agent_id") if isinstance(value.get("agent_id"), str) else None,
                   artifact=self.artifact(value.get("artifact"), path + ".artifact"),
                   execution=None, threshold_seconds=self.threshold)
        for field in ("summary", "agent_id"):
            if out[field] is None:
                self.absent(path + "." + field)
        self.timestamp(value.get("reported_at"), path + ".reported_at", out, "reported_at")
        parsed = _time(out["reported_at"])
        out["freshness"] = ("invalid" if value.get("reported_at") is not None and parsed is None
                            else "unknown" if parsed is None
                            else "invalid" if parsed > self.now
                            else "stale" if (self.now - parsed).total_seconds() > self.threshold else "fresh")
        if parsed and parsed > self.now:
            self.diag("INVALID_TIMESTAMP", "Future activity timestamp at " + path)
            self.absent(path + ".freshness", "invalid")
        execution = value.get("execution")
        if isinstance(execution, dict):
            ex = deepcopy(execution)
            status = ex.get("status")
            if not _member(status, {"running", "stopped", "unknown"}):
                status = "unknown"
                self.diag("UNKNOWN_STATUS", "Unknown execution status at " + path)
            artifact = self.artifact(execution.get("artifact"), path + ".execution.artifact")
            self.timestamp(execution.get("observed_at"), path + ".execution.observed_at", ex, "observed_at")
            observed = _time(ex.get("observed_at"))
            if (status != "unknown" and (not observed or observed > self.now or not artifact
                    or artifact["availability"]["status"] != "available")):
                status = "unknown"
                self.absent(path + ".execution.status")
            ex.update(status=status, artifact=artifact)
            out["execution"] = ex
        elif execution is not None:
            self.diag("INVALID_METADATA", "Invalid execution observation at " + path)
            self.absent(path + ".execution", "invalid")
        else:
            self.absent(path + ".execution")
        return out

    def history(self, entries, path):
        if entries is None:
            self.absent(path)
            return []
        if not isinstance(entries, list):
            self.diag("INVALID_METADATA", "Invalid history at " + path)
            self.absent(path, "invalid")
            return []
        result = []
        for i, raw in enumerate(entries):
            loc = path + "." + str(i)
            if not isinstance(raw, dict) or not _text(raw.get("status")):
                self.diag("INVALID_METADATA", "Invalid history entry at " + loc)
                self.absent(loc, "invalid")
                continue
            entry = deepcopy(raw)
            entry["by"] = raw.get("by") if isinstance(raw.get("by"), str) else None
            entry["artifacts"] = self.artifact_list(raw.get("artifacts"), loc + ".artifacts")
            self.timestamp(raw.get("recorded_at"), loc + ".recorded_at", entry, "recorded_at")
            for field in ("answer", "disposition"):
                if field in raw:
                    entry[field] = self.answer(raw[field], loc + "." + field)
            result.append(entry)
        return result

    def answer(self, value, path):
        if value is None:
            return None
        if not isinstance(value, dict) or not _text(value.get("text")) or not _text(value.get("by")):
            self.diag("INVALID_METADATA", "Invalid answer/disposition at " + path)
            self.absent(path, "invalid")
            return None
        out = deepcopy(value)
        self.timestamp(value.get("recorded_at"), path + ".recorded_at", out, "recorded_at")
        out["artifacts"] = self.artifact_list(value.get("artifacts"), path + ".artifacts")
        return out

    def unknown_prerequisite(self, kind, value=None):
        if kind not in {"blockers", "feedback"}:
            return
        if kind == "feedback" and isinstance(value, dict) and value.get("blocking") is False:
            return
        targets = value.get("blocks") if isinstance(value, dict) else None
        if not isinstance(targets, list) or not all(_text(t) for t in targets):
            targets = None
        elif kind == "feedback" and not targets:
            targets = None
        self.unknown_prerequisites.append(targets)

    def resolution_references(self, raw, projected, *, required, local_availability):
        if not isinstance(raw, list):
            return "not_recorded" if raw is None else "invalid"
        if (required and not raw) or len(raw) != len(projected):
            return "invalid"
        for ref in raw:
            if (not isinstance(ref, dict) or not _member(ref.get("kind"), {"file", "uri"})
                    or not _text(ref.get("target"))
                    or (ref.get("sha256") is not None and not _digest(ref["sha256"]))
                    or (ref.get("revision") is not None and not _positive(ref["revision"]))
                    or ("artifact_id" in ref and (not isinstance(ref["artifact_id"], str)
                        or not _IDENT.fullmatch(ref["artifact_id"])))):
                return "invalid"
            if ref["kind"] == "uri":
                try:
                    valid_uri = ref.get("base") is None and bool(urlparse(ref["target"]).scheme)
                except ValueError:
                    valid_uri = False
                if not valid_uri:
                    return "invalid"
                # The writer accepts a recorded URI, not fetched remote proof.
                continue
            if local_availability:
                available = self.availability(ref["target"])
                if available["status"] != "available":
                    return available["reason"] or "not_recorded"
        return None

    def terminal_proof(self, kind, raw, out):
        timestamp = _time(out.get("resolved_at"))
        history = raw.get("history")
        last = history[-1] if isinstance(history, list) and history else None
        if (timestamp is None or not isinstance(last, dict)
                or last.get("status") != raw["status"] or not _text(last.get("by"))
                or _time(last.get("recorded_at")) != timestamp):
            return "invalid"
        if "artifacts" in last and not isinstance(last["artifacts"], list):
            return "invalid"
        projected_last = out["history"][-1] if out["history"] else None
        if projected_last is None:
            return "invalid"
        history_gap = self.resolution_references(last.get("artifacts", []),
                         projected_last["artifacts"], required=kind == "blockers",
                         local_availability=kind == "blockers")
        if history_gap:
            return history_gap
        if kind == "blockers":
            return self.resolution_references(raw.get("artifacts"), out["artifacts"],
                                               required=True, local_availability=True)
        response = raw.get("disposition")
        disposition = out["disposition"]
        if disposition is None or _time(disposition.get("recorded_at")) is None:
            return "invalid"
        return self.resolution_references(response.get("artifacts", []), disposition["artifacts"],
                                           required=False, local_availability=False)

    def entities(self, visibility, kind):
        raw = visibility.get(kind)
        if raw is None:
            self.absent(kind)
            self.unknown_prerequisite(kind)
            return []
        if not isinstance(raw, dict):
            self.diag("INVALID_METADATA", "Expected map at " + kind)
            self.absent(kind, "invalid")
            self.unknown_prerequisite(kind)
            return []
        singular = {"blockers": "blocker", "feedback": "feedback", "assignments": "assignment"}[kind]
        result = []
        for key, value in raw.items():
            path = kind + "." + str(key)
            if not _text(key) or not isinstance(value, dict):
                self.diag("INVALID_METADATA", "Invalid entity at " + path)
                self.absent(path, "invalid")
                self.unknown_prerequisite(kind, value)
                continue
            out = deepcopy(value)
            out.update(id=self.id + "/" + singular + "/" + quote(key, safe=""), **{singular + "_id": key})
            if kind == "assignments":
                if not _text(value.get("agent_id")):
                    self.diag("INVALID_METADATA", "Assignment lacks agent identity at " + path)
                    self.absent(path, "invalid")
                    continue
                out.update(role=value.get("role") if isinstance(value.get("role"), str) else None,
                           task_id=value.get("task_id") if isinstance(value.get("task_id"), str) else None,
                           last_activity=self.activity(value.get("last_activity"), path + ".last_activity"), chats=[])
                chats = value.get("chats", [])
                if not isinstance(chats, list):
                    self.diag("INVALID_METADATA", "Invalid chats at " + path)
                    self.absent(path + ".chats", "invalid")
                    chats = []
                for chat in chats:
                    if (isinstance(chat, dict) and _text(chat.get("provider")) and _text(chat.get("id"))
                            and (chat.get("uri") is None or isinstance(chat.get("uri"), str))):
                        out["chats"].append(dict(provider=chat["provider"], id=chat["id"], uri=chat.get("uri")))
                    else:
                        self.diag("INVALID_METADATA", "Invalid chat reference at " + path)
                        self.absent(path + ".chats", "invalid")
                out["chats"].sort(key=lambda c: (c["provider"], c["id"], c["uri"] or ""))
                for field in ("role", "task_id"):
                    if out[field] is None:
                        self.absent(path + "." + field, "not_applicable" if field == "task_id" else "not_recorded")
            else:
                statuses = {"open", "resolved"} if kind == "blockers" else {"open", "answered", "resolved", "withdrawn"}
                required = ("reason", "resolution_condition", "reported_by") if kind == "blockers" else ("question", "requester")
                if not _member(value.get("status"), statuses) or not all(_text(value.get(k)) for k in required):
                    self.diag("UNKNOWN_STATUS" if not _member(value.get("status"), statuses) else "INVALID_METADATA",
                              "Invalid " + singular + " record at " + path)
                    self.absent(path, "invalid")
                    self.unknown_prerequisite(kind, value)
                    continue
                if (not isinstance(value.get("blocks"), list)
                        or not all(_text(t) for t in value["blocks"])
                        or (kind == "feedback" and type(value.get("blocking")) is not bool)):
                    self.diag("INVALID_METADATA", "Invalid blocking targets at " + path)
                    self.absent(path, "invalid")
                    self.unknown_prerequisite(kind, value)
                    continue
                out["blocks"] = sorted(set(value["blocks"]))
                nullable = "responsible" if kind == "blockers" else "respondent"
                out[nullable] = value.get(nullable) if isinstance(value.get(nullable), str) else None
                if out[nullable] is None:
                    self.absent(path + "." + nullable)
                self.timestamp(value.get("recorded_at"), path + ".recorded_at", out, "recorded_at")
                self.timestamp(value.get("resolved_at"), path + ".resolved_at", out, "resolved_at")
                out["history"] = self.history(value.get("history"), path + ".history")
                if kind == "blockers":
                    out["artifacts"] = self.artifact_list(value.get("artifacts"), path + ".artifacts")
                else:
                    out["artifact"] = self.artifact(value.get("artifact"), path + ".artifact")
                    out["answer"] = self.answer(value.get("answer"), path + ".answer")
                    out["disposition"] = self.answer(value.get("disposition"), path + ".disposition")
                    for field in ("answer", "disposition"):
                        if out[field] is None:
                            self.absent(path + "." + field, "not_applicable")
                terminal = value["status"] == "resolved" or kind == "feedback" and value["status"] == "withdrawn"
                if terminal:
                    proof_gap = self.terminal_proof(kind, value, out)
                    if proof_gap:
                        self.diag("INVALID_METADATA", "Reported terminal status has unverified resolution/disposition proof at " + path)
                        self.absent(path, proof_gap)
                        self.absent(path + ".status", proof_gap)
                        self.unknown_prerequisite(kind, value)
            result.append(out)
        return sorted(result, key=lambda v: v["id"])

    def evidence(self, record, path, *, head=None, revision=None, kind=None, task_id=None, author=None):
        if record is None:
            self.absent(path)
            return dict(record=None, currency="missing", artifacts=[])
        if not isinstance(record, dict):
            self.diag("INVALID_METADATA", "Invalid evidence record at " + path)
            self.absent(path, "invalid")
            return dict(record=None, currency="unknown", artifacts=[])
        refs = []
        report = record.get("report")
        if report is not None:
            ref = report if isinstance(report, dict) else dict(kind="file", target=report, base="workspace", sha256=None, revision=record.get("spec_revision"))
            logical = None
            if _text(record.get("head")) and _positive(record.get("spec_revision")):
                logical = (("review:" + task_id) if task_id else ("gate:" + kind)) + ":" + record["head"] + ":" + str(record["spec_revision"]) if task_id or kind else None
            item = self.artifact(ref, path + ".report", logical)
            if item:
                refs.append(item)
        valid_targets = _text(head) and _positive(revision) and _text(record.get("head")) and _positive(record.get("spec_revision"))
        currency = "unknown"
        if valid_targets and (record["head"] != head or record["spec_revision"] != revision):
            currency = "obsolete"
        elif valid_targets and self.current_approval:
            if kind:
                complete = type(record.get("passed")) is bool and _text(record.get("agent")) and bool(record.get("evidence"))
                all_authors = {t.get("owner") for t in self.state["tasks"].values() if isinstance(t.get("owner"), str)}
                complete = complete and record.get("agent") not in all_authors
            else:
                complete = (_text(record.get("agent")) and record.get("agent") != author
                            and _member(record.get("verdict"), {"pass", "fail"}) and bool(record.get("tests"))
                            and isinstance(record.get("findings"), list))
            reference_valid = ((report is None or bool(refs))
                               and not any(k.startswith(path + ".") and r in _GAPS
                                           for k, r in self.unavailable.items()))
            if complete and reference_valid and all(a["kind"] == "file" and a["availability"]["status"] == "available" for a in refs):
                currency = "current"
        if currency == "unknown":
            self.absent(path + ".currency")
        return dict(record=deepcopy(record), currency=currency, artifacts=refs)


def _pending_integration(p, tasks):
    """Classify the supported helper's persisted intent, never dict truthiness."""
    intent = p.state.get("integration")
    if intent is None:
        return "missing", False

    def unknown(message, path="integration", reason="invalid", code="INVALID_METADATA"):
        p.absent(path, reason)
        p.diag(code, message)
        return "unknown", False

    if not isinstance(intent, dict):
        return unknown("Integration intent must be a recorded object")
    if (not all(_text(intent.get(k)) for k in ("task", "source_head", "parent", "phase"))
            or not _positive(intent.get("spec_revision"))):
        return unknown("Integration intent lacks typed task/source_head/parent/spec_revision/phase evidence")
    if intent["phase"] != "prepared":
        return unknown("Unsupported pending integration phase: " + intent["phase"],
                       "integration.phase", "unsupported", "UNKNOWN_STATUS")
    source_task = tasks.get(intent["task"])
    if not isinstance(source_task, dict):
        return unknown("Integration intent references an unknown produced task", "integration.task")
    current_head = p.state.get("integrated_head")
    revision = p.state.get("spec_revision")
    if not _text(source_task.get("head")) or not _text(current_head) or not _positive(revision):
        return unknown("Integration intent lacks recorded current task/head/specification bindings")
    if (intent["source_head"] != source_task["head"] or intent["parent"] != current_head
            or intent["spec_revision"] != revision):
        p.absent("integration.currency", "inconsistent")
        p.diag("INVALID_METADATA", "Integration intent targets no longer match recorded task/head/specification")
        return "obsolete", False
    if source_task.get("status") != "reviewed":
        return unknown("Prepared integration intent is not bound to a reviewed source task",
                       "integration.task_status")
    if not p.current_approval:
        p.absent("integration.currency")
        return "unknown", False
    return "current", True


def _completion_evidence(p, lifecycle, pr, cleanup):
    """Check recorded bindings only; this is not live merge/resource verification."""
    state = p.state
    publication, merge = state.get("pr"), state.get("merge")
    resources = state.get("resources")
    resources = resources if isinstance(resources, dict) else {}
    plan, authorization = state.get("cleanup"), state.get("cleanup_authorization")
    items = plan.get("items") if isinstance(plan, dict) else None
    removed = {key for key, value in resources.items()
               if isinstance(value, dict) and value.get("status") == "removed"}
    started = isinstance(items, list) and any(isinstance(i, dict)
               and i.get("status") in ("removing", "removed") for i in items)
    feature_removed = any(resources[k].get("kind") == "worktree"
                          and resources[k].get("purpose") == "feature" for k in removed)
    merge_required = lifecycle in {"merged", "cleanup_pending", "closed"} or merge is not None or feature_removed

    def issue(path, message, reason="invalid", obsolete=False):
        p.absent(path, reason)
        p.diag("INVALID_METADATA", message)
        cleanup["currency"] = "obsolete" if obsolete else "unknown"
        if path.startswith("merge"):
            pr["currency"] = "obsolete" if obsolete else "unknown"

    if merge_required:
        valid_merge = (isinstance(merge, dict) and all(_text(merge.get(k))
                       for k in ("commit", "head", "base"))
                       and bool(merge.get("evidence"))
                       and isinstance(publication, dict)
                       and all(_text(publication.get(k)) for k in ("url", "head", "base"))
                       and bool(publication.get("evidence")))
        if not valid_merge:
            issue("merge", "Required recorded merge/publication proof is missing or incomplete",
                  "not_recorded" if merge is None else "invalid")
        elif merge["head"] != publication["head"] or merge["base"] != publication["base"]:
            issue("merge", "Recorded merge is not bound to the published head/base", obsolete=True)
        elif merge["head"] != state.get("integrated_head"):
            issue("merge", "Recorded merge targets an obsolete integrated head", obsolete=True)

    execution_claimed = started or lifecycle == "closed"
    if plan is None and not execution_claimed:
        for key in sorted(removed):
            p.absent("cleanup.prior_removal." + key)
            cleanup["currency"] = "unknown"
        return
    if not isinstance(plan, dict):
        issue("cleanup", "Cleanup execution/completion lacks a recorded inventory",
              "not_recorded" if plan is None else "invalid")
        return
    inventory = plan.get("inventory")
    valid_inventory = (isinstance(inventory, list) and bool(inventory)
                       and all(isinstance(i, dict) and _text(i.get("resource_id")) for i in inventory)
                       and len({i["resource_id"] for i in inventory}) == len(inventory))
    valid_items = (isinstance(items, list) and all(isinstance(i, dict)
                   and _text(i.get("resource_id")) and isinstance(i.get("status"), str)
                   and i["status"] in {"pending", "removing", "removed"} for i in items)
                   and len({i["resource_id"] for i in items}) == len(items))
    if not valid_inventory or not valid_items:
        issue("cleanup.inventory", "Recorded cleanup inventory/items are missing or malformed")
        return
    snapshots = {i["resource_id"]: i for i in inventory}
    item_map = {i["resource_id"]: i for i in items}
    if set(snapshots) != set(item_map):
        issue("cleanup.inventory", "Cleanup items do not match the recorded inventory")
    try:
        digest = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
    except (TypeError, ValueError):
        digest = None
    if not _digest(plan.get("inventory_sha256")) or digest != plan["inventory_sha256"]:
        issue("cleanup.inventory_sha256", "Recorded cleanup inventory digest does not match its contents")
    if started:
        valid_authorization = (isinstance(authorization, dict)
                               and all(_text(authorization.get(k)) for k in ("human", "evidence", "date"))
                               and authorization.get("feature_id") == state.get("feature_id")
                               and _digest(authorization.get("inventory_sha256"))
                               and authorization["inventory_sha256"] == plan.get("inventory_sha256"))
        if valid_authorization:
            try:
                valid_authorization = date.fromisoformat(authorization["date"]).isoformat() == authorization["date"]
            except (TypeError, ValueError):
                valid_authorization = False
        if not valid_authorization:
            issue("cleanup_authorization", "Cleanup execution/completion lacks matching feature/inventory authorization",
                  "not_recorded" if authorization is None else "invalid")
    for key, item in item_map.items():
        resource, snapshot = resources.get(key), snapshots.get(key)
        if not isinstance(resource, dict) or not isinstance(snapshot, dict):
            issue("cleanup.items." + key, "Cleanup item lacks its recorded resource/inventory binding")
            continue
        kind = resource.get("kind")
        identity_valid = (isinstance(kind, str) and kind in {"worktree", "directory", "container", "network"}
                          and _text(resource.get("owner")) and _text(resource.get("purpose")))
        if kind in ("worktree", "directory"):
            path = resource.get("path")
            absolute = (_text(path) and (path.startswith("/") or path.startswith(chr(92) * 2)
                        or (len(path) > 2 and path[1] == ":" and path[2] in ("/", chr(92)))))
            identity_valid = identity_valid and absolute
        elif kind in ("container", "network"):
            identity_valid = identity_valid and _digest(resource.get("docker_id"))
        if kind == "worktree":
            identity_valid = identity_valid and _text(resource.get("branch")) and _text(snapshot.get("head"))
        if not identity_valid:
            issue("cleanup.items." + key, "Cleanup resource lacks its recorded exact identity/ownership")
        fields = ("kind", "owner", "purpose", "path", "branch", "docker_id", "task_id")
        if any(resource.get(k) != snapshot.get(k) for k in fields):
            issue("cleanup.items." + key, "Cleanup inventory no longer matches the recorded resource")
        if item["status"] == "removed":
            if resource.get("status") != "removed" or item.get("error"):
                issue("cleanup.items." + key, "Recorded removal is incomplete, failed or inconsistent")
            if snapshot.get("kind") == "worktree" and not _text(snapshot.get("head")):
                issue("cleanup.items." + key, "Worktree removal lacks recorded source HEAD preservation evidence")
        elif resource.get("status") == "removed":
            issue("cleanup.items." + key, "Resource removal is not backed by a completed cleanup item")
    # cleanup_plan may replace a completed inventory. Earlier removed resources
    # legitimately remain in the manifest, with their old proof in checkpoints
    # rather than this latest plan. Absence of that history is not corruption.
    for key in sorted(removed - set(item_map)):
        p.absent("cleanup.prior_removal." + key)
        cleanup["currency"] = "unknown"
    if lifecycle == "closed":
        if not resources or any(not isinstance(v, dict) or v.get("status") != "removed"
                                for v in resources.values()):
            issue("cleanup.closeout", "Closed lifecycle lacks recorded removal of all registered resources")
        if any(item_map[k]["status"] != "removed" for k in item_map):
            issue("cleanup.closeout", "Closed lifecycle has unfinished items in its current cleanup inventory")


def project_feature(state, *, repository_id, workspace_id, source_id, now,
                    freshness_seconds=3600, artifact_status=None):
    """Return (feature or None, diagnostics), without changing any input.

    Availability supplied by the reader is keyed by original artifact target;
    "available" for a local digest-bound artifact means its bytes were verified.
    No availability status for a URI asserts remote verification.
    """
    observed = _now(now)
    if not _positive(freshness_seconds):
        raise ValueError("freshness_seconds must be a positive integer")
    if not all(isinstance(v, str) and _IDENT.fullmatch(v) for v in (repository_id, workspace_id)):
        raise ValueError("repository_id and workspace_id must be stable configured identifiers")
    diagnostics = []
    def reject(code, message):
        return None, [dict(code=code, message=message, source_id=source_id, entity_id=None)]
    if not isinstance(state, dict):
        return reject("INVALID_SOURCE", "State must be an object")
    if (type(state.get("schema_version")) is not int or state["schema_version"] != 2
            or not isinstance(state.get("library_version"), str)
            or not re.fullmatch(r"1\.\d+\.\d+", state["library_version"])):
        return reject("UNSUPPORTED_SOURCE", "Only state schema 2 and library major 1 are supported")
    if not _text(state.get("feature_id")):
        return reject("INVALID_SOURCE", "Missing feature identity")
    visibility = state.get("visibility")
    if visibility is not None:
        if not isinstance(visibility, dict):
            return reject("INVALID_METADATA", "Visibility metadata must be an object")
        if not isinstance(visibility.get("version"), str) or not re.fullmatch(r"1\.\d+\.\d+", visibility["version"]):
            return reject("UNSUPPORTED_SOURCE", "Unsupported visibility metadata version")
    if artifact_status is not None and not isinstance(artifact_status, dict):
        raise ValueError("artifact_status must be a target-keyed map")
    p = _Projection(state, repository_id, workspace_id, source_id, observed,
                    freshness_seconds, artifact_status or {})
    if not p.eligibility():
        return None, sorted(p.diagnostics, key=_diagnostic_key)
    metadata = visibility or {}
    blockers = p.entities(metadata, "blockers")
    feedback = p.entities(metadata, "feedback")
    assignments = p.entities(metadata, "assignments")
    activity = p.activity(metadata.get("activity"), "activity")
    tasks = state["tasks"]
    graph_valid = True
    edges = {}
    for key, raw in tasks.items():
        dependencies = raw.get("depends_on")
        valid = (isinstance(dependencies, list) and all(_text(d) for d in dependencies)
                 and len(set(dependencies)) == len(dependencies)
                 and all(d in tasks for d in dependencies)
                 and isinstance(raw.get("status"), str) and raw["status"] in _TASK_STATES)
        edges[key] = dependencies if isinstance(dependencies, list) and all(_text(d) for d in dependencies) else []
        if not valid:
            graph_valid = False
            p.diag("INVALID_DEPENDENCIES", "Invalid dependencies or task status for " + key,
                   p.id + "/task/" + quote(key, safe=""))
    # Iterative traversal avoids recursion failure on long, otherwise valid plans.
    colors = {}
    for start in tasks:
        stack = [(start, False)]
        while stack:
            key, exiting = stack.pop()
            if exiting:
                colors[key] = 2
                continue
            if colors.get(key) == 1:
                graph_valid = False
                p.diag("INVALID_DEPENDENCIES", "Dependency cycle at " + key)
                continue
            if colors.get(key) == 2:
                continue
            colors[key] = 1
            stack.append((key, True))
            stack.extend((d, False) for d in reversed(edges[key]) if d in tasks)
    phases = set()
    lifecycle = state.get("lifecycle")
    if not isinstance(lifecycle, str) or lifecycle not in _LIFECYCLES:
        lifecycle = None
        p.absent("lifecycle", "unsupported" if state.get("lifecycle") is not None else "not_recorded")
        p.diag("UNKNOWN_STATUS", "Unknown or missing feature lifecycle")
    phase_for_lifecycle = {"published": "published", "merged": "merged",
                           "cleanup_pending": "awaiting_cleanup", "closed": "closed"}
    if lifecycle in phase_for_lifecycle:
        phases.add(phase_for_lifecycle[lifecycle])
    operations = metadata.get("phases")
    if operations is None:
        p.absent("phases.operations")
    elif not isinstance(operations, list):
        p.diag("INVALID_METADATA", "Operation phases must be an array")
        p.absent("phases.operations", "invalid")
    else:
        operation_ids = set()
        for operation in operations:
            if (not isinstance(operation, dict) or not _text(operation.get("id"))
                    or operation.get("id") in operation_ids
                    or not isinstance(operation.get("phase"), str)
                    or operation["phase"] not in {"investigating", "awaiting_specification_approval", "integrating", "validating"}
                    or not isinstance(operation.get("status"), str)
                    or operation["status"] not in {"active", "finished"}):
                p.diag("INVALID_METADATA", "Invalid or duplicate operation phase record")
                continue
            operation_ids.add(operation["id"])
            ref = p.artifact(operation.get("artifact"), "phases." + operation["id"] + ".artifact")
            if (operation["status"] == "active" and _time(operation.get("reported_at"))
                    and _time(operation["reported_at"]) <= observed and ref
                    and ref["availability"]["status"] == "available"):
                phases.add(operation["phase"])
            elif operation["status"] == "active":
                p.absent("phases." + operation["id"], "invalid")
                p.diag("INVALID_METADATA", "Active operation lacks valid reported evidence")
    pending_integration_currency, active_integration = _pending_integration(p, tasks)
    if active_integration:
        phases.add("integrating")
    reviews = {}
    projected_tasks = []
    control = metadata.get("control")
    control_ref = p.artifact(control.get("evidence"), "control.evidence") if isinstance(control, dict) else None
    control_known = (isinstance(control, dict) and control.get("owner_role") == "orchestrator"
                     and type(control.get("execution_authorized")) is bool and control_ref is not None
                     and control_ref["availability"]["status"] == "available")
    for key in sorted(tasks):
        raw = tasks[key]
        status = raw.get("status")
        if not isinstance(status, str) or status not in _TASK_STATES:
            status = None
            p.diag("UNKNOWN_STATUS", "Unknown task status for " + key)
            p.absent("tasks." + key + ".status", "unsupported")
        owner = raw.get("owner") if isinstance(raw.get("owner"), str) else None
        if status == "pending":
            phases.add("planned")
        elif status == "implementing":
            phases.add("implementing")
        elif status in {"review", "reviewed"}:
            phases.add("under_review")
        review = p.evidence(raw.get("review"), "reviews." + key, head=raw.get("head"),
                            revision=state.get("spec_revision"), task_id=key, author=owner)
        reviews[key] = review
        deps = sorted(set(edges[key]))
        waiting = [d for d in deps if d not in tasks or tasks[d].get("status") != "complete"]
        dependencies = ("not_applicable" if status != "pending" else "invalid" if not graph_valid
                        else "waiting" if waiting else "ready")
        reasons = []
        eligible = False
        if status != "pending":
            reasons.append("task_not_pending")
        elif dependencies != "ready":
            reasons.append("invalid_dependencies" if dependencies == "invalid" else "dependencies_incomplete")
        else:
            targets = {"feature", "task:" + key, "phase:implementing", "phase:planned"}
            blocked = any(b["status"] == "open" and targets.intersection(b["blocks"]) for b in blockers)
            feedback_wait = any(f["blocking"] and f["status"] in {"open", "answered"}
                                and targets.intersection(f["blocks"]) for f in feedback)
            uncertain = any(scope is None or targets.intersection(scope)
                            for scope in p.unknown_prerequisites)
            if blocked or feedback_wait or state.get("integration") is not None:
                reasons += (["explicit_blocker"] if blocked else []) + (["human_feedback"] if feedback_wait else [])
                if state.get("integration") is not None:
                    reasons.append("unresolved_integration")
            elif isinstance(control, dict) and control.get("execution_authorized") is False:
                reasons.append("execution_not_authorized")
            elif control_known and p.current_approval and not uncertain:
                eligible = True
            else:
                eligible = None
                reasons.append("unverified_prerequisites")
                p.absent("tasks." + key + ".readiness.start_eligible")
        projected_tasks.append(dict(id=p.id + "/task/" + quote(key, safe=""), task_id=key,
                                    status=status, depends_on=deps,
                                    dependency_status=[dict(task_id=d, status=(tasks[d].get("status")
                                        if d in tasks and isinstance(tasks[d].get("status"), str)
                                        and tasks[d]["status"] in _TASK_STATES else None)) for d in deps],
                                    readiness=dict(dependencies=dependencies, waiting_on=waiting,
                                                   start_eligible=eligible, reasons=reasons),
                                    owner=owner, review=review))
        if owner and not any(a["agent_id"] == owner and a["task_id"] == key for a in assignments):
            local = "task-owner:" + key
            assignments.append(dict(id=p.id + "/assignment/" + quote(local, safe=""),
                                    assignment_id=local, agent_id=owner, role=None,
                                    task_id=key, last_activity=None, chats=[]))
            p.absent("assignments." + local + ".role")
            p.absent("assignments." + local + ".last_activity")
            p.absent("assignments." + local + ".chats")
    gates = state.get("gates")
    if not isinstance(gates, dict):
        gates = {}
        p.absent("gates", "invalid" if state.get("gates") is not None else "not_recorded")
    projected_gates = {kind: p.evidence(gates.get(kind), "gates." + kind,
                                      head=state.get("integrated_head"), revision=state.get("spec_revision"), kind=kind)
                       for kind in ("validation", "quality")}
    integration_record = state.get("integration")
    if integration_record is None:
        completed = {k: deepcopy(t["integration_evidence"]) for k, t in tasks.items()
                     if isinstance(t.get("integration_evidence"), dict)}
        integration_record = dict(completed=completed) if completed else None
    integration = dict(record=deepcopy(integration_record) if isinstance(integration_record, dict) else None,
                       currency="unknown" if integration_record is not None else "missing", artifacts=[])
    if integration_record is None:
        p.absent("integration")
    elif state.get("integration") is not None:
        integration["currency"] = pending_integration_currency
    else:
        outcomes = []
        for key, record in integration_record["completed"].items():
            source_task = tasks[key]
            if record.get("spec_revision") != state.get("spec_revision"):
                outcomes.append("obsolete")
            else:
                checks = record.get("tests")
                checks_pass = (isinstance(checks, list) and bool(checks)
                               and all(isinstance(c, dict) and type(c.get("exit_code")) is int
                                       and c["exit_code"] == 0 for c in checks))
                consistent = (p.current_approval and _text(record.get("commit"))
                              and record["commit"] == source_task.get("integration_commit")
                              and _text(record.get("source_head"))
                              and record["source_head"] == source_task.get("head")
                              and _text(record.get("parent")) and _text(record.get("tree"))
                              and checks_pass)
                outcomes.append("current" if consistent else "unknown")
        integration["currency"] = ("obsolete" if "obsolete" in outcomes else
                                   "current" if outcomes and all(v == "current" for v in outcomes)
                                   else "unknown")
    pr_raw = state.get("pr")
    pr = dict(record=None, currency="missing", artifacts=[])
    if pr_raw is None:
        p.absent("pr", "not_applicable")
    elif not isinstance(pr_raw, dict):
        p.diag("INVALID_METADATA", "Invalid PR record")
        p.absent("pr", "invalid")
        pr["currency"] = "unknown"
    else:
        pr["record"] = dict(pr=deepcopy(pr_raw), merge=deepcopy(state.get("merge")))
        pr["currency"] = ("obsolete" if _text(pr_raw.get("head")) and pr_raw["head"] != state.get("integrated_head")
                          else "current" if p.current_approval and all(_text(pr_raw.get(k)) for k in ("url", "head", "base"))
                          and bool(pr_raw.get("evidence")) else "unknown")
    cleanup_fields = ("resources", "cleanup", "cleanup_authorization", "lifecycle", "merge")
    cleanup = dict(record={k: deepcopy(state.get(k)) for k in cleanup_fields},
                   currency="current" if p.current_approval and isinstance(state.get("resources"), dict) and lifecycle else "unknown",
                   artifacts=[])
    for field in ("cleanup", "cleanup_authorization", "merge"):
        if state.get(field) is not None and not isinstance(state[field], dict):
            p.diag("INVALID_METADATA", "Invalid recorded " + field)
            p.absent(field, "invalid")
            cleanup["currency"] = "unknown"
            if field == "merge":
                pr["currency"] = "unknown"
    _completion_evidence(p, lifecycle, pr, cleanup)
    feature = dict(id=p.id, repository_id=repository_id, workspace_id=workspace_id,
                   feature_id=state["feature_id"], source_id=source_id,
                   availability=dict(status="available", reason=None), lifecycle=lifecycle,
                   phases=sorted(phases), tasks=projected_tasks, blockers=blockers, feedback=feedback,
                   assignments=sorted(assignments, key=lambda a: a["id"]), activity=activity,
                   reviews=reviews, integration=integration, gates=projected_gates, pr=pr,
                   cleanup=cleanup, artifacts=p.artifacts, unavailable=p.unavailable, diagnostics=p.diagnostics)
    if p.collision_ids:
        # A collision invalidates every reference to that identity, including
        # earlier nested references, and prevents a current-evidence claim.
        def invalidate(value):
            if isinstance(value, dict):
                if isinstance(value.get("id"), str) and value["id"] in p.collision_ids:
                    value.update(id=None, identity_source="unavailable", identity_reason="invalid")
                if value.get("currency") == "current" and "record" in value:
                    value["currency"] = "unknown"
                for v in value.values():
                    invalidate(v)
            elif isinstance(value, list):
                for v in value:
                    invalidate(v)
        invalidate(feature)
    feature["artifacts"].sort(key=lambda a: (a["id"] or "", a["target"]))
    feature["diagnostics"].sort(key=_diagnostic_key)
    if p.partial:
        feature["availability"] = dict(status="partial", reason="invalid" if p.diagnostics else
                                       next((r for r in p.unavailable.values() if r in _GAPS), "invalid"))
    return feature, feature["diagnostics"]
