"""Contract declarations and synthetic consumer examples; standard library only.

These focused checks do not implement a JSON Schema validator. Developers may
also use a draft 2020-12 validator against snapshot-schema.json; none is an
installed helper or test-suite dependency.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import unittest
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "skills/feature-workflow/references"
EXAMPLES = ROOT / "skills/feature-workflow/assets/snapshot-examples"


class SnapshotContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((REFERENCE / "snapshot-schema.json").read_text())
        cls.defs = cls.schema["$defs"]
        cls.examples = {
            name: json.loads((EXAMPLES / (name + ".json")).read_text())
            for name in ("complete", "partial", "unavailable")
        }

    def test_all_local_schema_references_resolve(self):
        def inspect(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    self.assertTrue(value["$ref"].startswith("#/$defs/"))
                    self.assertIn(value["$ref"].removeprefix("#/$defs/"), self.defs)
                for item in value.values():
                    inspect(item)
            elif isinstance(value, list):
                for item in value:
                    inspect(item)
        inspect(self.schema)
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", self.schema["$schema"])

    def test_version_contract_accepts_compatible_minor_not_unknown_major_or_types(self):
        pattern = self.defs["version"]["pattern"]
        self.assertEqual("string", self.defs["version"]["type"])
        for value in ("1.0.0", "1.3.2"):
            self.assertIsNotNone(re.fullmatch(pattern, value))
        for value in ("2.0.0", "0.9.0", "1", "1.0", "1.0.0-beta", 1, True, None):
            accepted = isinstance(value, str) and re.fullmatch(pattern, value) is not None
            self.assertFalse(accepted, value)

    def test_every_envelope_contains_required_fields_and_typed_collections(self):
        for envelope in self.examples.values():
            self.assertTrue(set(self.schema["required"]) <= envelope.keys())
            self.assertIn(envelope["completeness"], self.schema["properties"]["completeness"]["enum"])
            self.assertEqual("feature-workflow", envelope["producer"]["name"])
            for key in ("sources", "features", "diagnostics"):
                self.assertIs(type(envelope[key]), list)
                self.assertEqual("array", self.schema["properties"][key]["type"])

    def test_sources_and_features_have_complete_required_shapes(self):
        for envelope in self.examples.values():
            for source in envelope["sources"]:
                self.assertTrue(set(self.defs["source"]["required"]) <= source.keys())
                self.assertIn(source["status"], self.defs["source"]["properties"]["status"]["enum"])
            for feature in envelope["features"]:
                self.assertTrue(set(self.defs["feature"]["required"]) <= feature.keys())
                self.assertIn(feature["lifecycle"], self.defs["feature"]["properties"]["lifecycle"]["anyOf"][0]["enum"])
                for task in feature["tasks"]:
                    self.assertTrue(set(self.defs["task"]["required"]) <= task.keys())
                    self.assertIn(task["status"], self.defs["task"]["properties"]["status"]["anyOf"][0]["enum"])
                    self.assertIs(type(task["readiness"]["start_eligible"]), bool)
                for key in ("integration", "pr", "cleanup"):
                    self.assertTrue(set(self.defs["evidence"]["required"]) <= feature[key].keys())
                for assignment in feature["assignments"]:
                    self.assertTrue(set(self.defs["assignment"]["required"]) <= assignment.keys())

    def test_unknown_status_and_false_success_are_not_declared_values(self):
        fields = [
            (self.defs["task"]["properties"]["status"]["anyOf"][0], "running"),
            (self.defs["evidence"]["properties"]["currency"], "passed"),
            (self.defs["feedback"]["properties"]["status"], "approved"),
            (self.defs["source"]["properties"]["status"], "repaired"),
        ]
        for declaration, invalid in fields:
            self.assertNotIn(invalid, declaration["enum"])
        eligible = self.defs["task"]["properties"]["readiness"]["properties"]["start_eligible"]
        self.assertEqual([{"type": "boolean"}, {"type": "null"}], eligible["anyOf"])
        self.assertNotEqual(type("true"), bool)
        self.assertNotEqual(type(1), bool)

    def test_unavailable_values_are_explicit_and_independent_of_blockers(self):
        expected = {
            "not_recorded", "not_applicable", "missing", "inaccessible",
            "invalid", "unsupported", "inconsistent",
        }
        self.assertEqual(expected, set(self.defs["reason"]["enum"]))
        feature = self.examples["complete"]["features"][0]
        self.assertEqual([], feature["blockers"])
        self.assertEqual("not_recorded", feature["unavailable"]["gates.validation"])
        self.assertEqual("missing", feature["gates"]["validation"]["currency"])

    def test_partial_result_retains_healthy_feature_and_missing_source(self):
        partial = self.examples["partial"]
        self.assertEqual("partial", partial["completeness"])
        self.assertEqual(self.examples["complete"]["features"], partial["features"])
        self.assertEqual(["available", "missing"], [s["status"] for s in partial["sources"]])
        self.assertEqual("MISSING_SOURCE", partial["diagnostics"][0]["code"])
        self.assertIsNone(partial["sources"][1]["generation"])
        self.assertIsNone(partial["sources"][1]["state_sha256"])

    def test_fatal_result_has_json_diagnostics_and_no_guessed_features(self):
        fatal = self.examples["unavailable"]
        self.assertEqual("unavailable", fatal["completeness"])
        self.assertEqual([], fatal["sources"])
        self.assertEqual([], fatal["features"])
        self.assertEqual("INVALID_CONFIG", fatal["diagnostics"][0]["code"])

    def test_timestamp_digest_and_read_attempt_constraints(self):
        stamp = self.defs["timestamp"]
        self.assertEqual("date-time", stamp["format"])
        self.assertIsNotNone(re.fullmatch(stamp["pattern"], "2026-11-06T20:00:00Z"))
        self.assertIsNone(re.fullmatch(stamp["pattern"], "2026-11-06"))
        self.assertIsNone(re.fullmatch(stamp["pattern"], "2026-11-06T20:00:00"))
        digest = self.defs["digest"]["pattern"]
        self.assertIsNotNone(re.fullmatch(digest, "a" * 64))
        self.assertIsNone(re.fullmatch(digest, "historical time invented"))
        attempts = self.defs["config"]["properties"]["max_read_attempts"]
        self.assertEqual(("integer", 1, 3), (attempts["type"], attempts["minimum"], attempts["maximum"]))

    def test_initial_publication_requires_nonempty_tasks_and_retained_binding(self):
        marker = self.defs["eligibility"]
        self.assertTrue({"spec_revision", "spec_sha256", "approval", "task_ids", "recorded_at"} <= set(marker["required"]))
        self.assertEqual(1, marker["properties"]["task_ids"]["minItems"])
        self.assertTrue({"human", "evidence", "date", "revision", "sha256"} <= set(marker["properties"]["approval"]["required"]))
        text = (REFERENCE / "snapshot.md").read_text()
        self.assertIn("independently of the current/latest specification", text)
        self.assertIn("empty task list", text)
        self.assertIn("actual nonempty referenced tasks", text)

    def test_synthetic_config_uses_explicit_identity_and_locations(self):
        config = json.loads((EXAMPLES / "config.json").read_text())
        self.assertEqual("1.0.0", config["config_version"])
        self.assertTrue(config["repositories"])
        self.assertTrue(config["workspace_roots"])
        self.assertEqual(config["repositories"][0]["id"], config["workspace_roots"][0]["repository_id"])
        self.assertEqual(3, config["max_read_attempts"])
        self.assertEqual("string", self.defs["identifier"]["type"])

    def test_compatible_optional_fields_are_not_forbidden(self):
        for name in ("feature", "source", "task", "evidence"):
            self.assertIs(self.defs[name]["additionalProperties"], True)
        extended = copy.deepcopy(self.examples["complete"])
        extended["future_optional_field"] = {"note": "ignored by a 1.0 consumer"}
        self.assertTrue(set(self.schema["required"]) <= extended.keys())



    def test_artifact_schema_requires_honest_scoped_identity_fields(self):
        artifact = self.defs["artifact"]
        self.assertTrue({"id", "identity_source", "identity_reason"} <= set(artifact["required"]))
        self.assertEqual(
            [{"type": "string", "minLength": 1}, {"type": "null"}],
            artifact["properties"]["id"]["anyOf"],
        )
        self.assertEqual(
            {"recorded", "logical", "content", "unavailable"},
            set(artifact["properties"]["identity_source"]["enum"]),
        )
        for envelope in self.examples.values():
            for feature in envelope["features"]:
                for ref in feature["artifacts"]:
                    self.assertTrue({"id", "identity_source", "identity_reason"} <= ref.keys())
                    self.assertTrue(ref["id"].startswith(feature["id"] + "/artifact/"))

    def test_reference_artifact_ids_survive_relocation_and_unknown_digest(self):
        # Tiny reference consumer of the identity rule, not a runtime helper.
        def identity(source, context, feature_id):
            local = None
            origin = "unavailable"
            recorded = source.get("artifact_id")
            if isinstance(recorded, str) and re.fullmatch(self.defs["identifier"]["pattern"], recorded):
                local, origin = "recorded:" + recorded, "recorded"
            elif context.get("role") == "ticket":
                local, origin = "ticket", "logical"
            elif context.get("role") == "spec" and type(context.get("revision")) is int and context["revision"] > 0:
                local, origin = "spec:" + str(context["revision"]), "logical"
            elif isinstance(source.get("sha256"), str) and re.fullmatch(self.defs["digest"]["pattern"], source["sha256"]):
                local, origin = "sha256:" + source["sha256"], "content"
            return (
                feature_id + "/artifact/" + quote(local, safe="") if local else None,
                origin,
                None if local else "not_recorded",
            )
        cases = json.loads((EXAMPLES / "artifact-identity-cases.json").read_text())
        for case in cases:
            self.assertEqual(
                (case["expected_id"], case["expected_source"], case["expected_reason"]),
                identity(case["source"], case["context"], case["feature_id"]),
                case["name"],
            )
        # An attractive filename is not evidence of logical role.
        self.assertEqual(
            (None, "unavailable", "not_recorded"),
            identity({"target": "/moved/ticket.md", "sha256": None}, {}, "demo/sample/sample"),
        )

    def test_duplicate_refs_share_identity_without_positional_keys(self):
        cases = {
            item["name"]: item
            for item in json.loads((EXAMPLES / "artifact-identity-cases.json").read_text())
        }
        before = cases["ticket-before-relocation"]
        after = cases["ticket-after-relocation"]
        self.assertNotEqual(before["source"]["target"], after["source"]["target"])
        self.assertEqual(before["expected_id"], after["expected_id"])
        self.assertEqual(1, len({before["expected_id"], after["expected_id"]}))
        self.assertIsNone(before["source"]["sha256"])
        self.assertIsNone(after["source"]["sha256"])
        unknown = cases["legacy-unidentified-report"]
        self.assertIsNone(unknown["expected_id"])
        self.assertEqual("not_recorded", unknown["expected_reason"])
        text = (REFERENCE / "snapshot.md").read_text()
        self.assertIn("both conflicting references", text)
        self.assertIn("Availability lookup remains independently keyed", text)
        self.assertIn("emit it only once in feature.artifacts", text)

        def nested_ids(value):
            if isinstance(value, dict):
                if "kind" in value and "identity_source" in value and value["id"] is not None:
                    yield value["id"]
                for item in value.values():
                    yield from nested_ids(item)
            elif isinstance(value, list):
                for item in value:
                    yield from nested_ids(item)
        for envelope in self.examples.values():
            for feature in envelope["features"]:
                canonical = [ref["id"] for ref in feature["artifacts"]]
                self.assertEqual(len(canonical), len(set(canonical)))
                self.assertEqual(set(canonical), set(nested_ids(feature)))


if __name__ == "__main__":
    unittest.main()
