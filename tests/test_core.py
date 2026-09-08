"""Independent end-to-end checks using owned synthetic JUnit artifacts only."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from runsignal.analysis import snapshot
from runsignal.ingest import ingest
import importlib

ingest_module = importlib.import_module("runsignal.ingest")


def case(name="test_box", status="passed", time="1", **attributes):
    return {"name": name, "status_kind": status, "time": time, **attributes}


def junit(cases, suite="suite", namespace=False):
    root = ET.Element("testsuite", {"name": suite})
    for item in cases:
        values = dict(item)
        status = values.pop("status_kind", "passed")
        duration = values.pop("time", None)
        attrs = {"classname": "tests.products", "file": "tests/test_products.py", **values}
        if duration is not None:
            attrs["time"] = str(duration)
        node = ET.SubElement(root, "testcase", attrs)
        if status != "passed":
            ET.SubElement(node, {"failed": "failure", "error": "error",
                                 "skipped": "skipped"}.get(status, status))
    if namespace:
        root.set("xmlns", "urn:synthetic:junit")
    return ET.tostring(root, encoding="utf-8")


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.db = self.base / "history.sqlite3"
        self.manifest = self.base / "manifest.json"
        self.serial = 0

    def report(self, data, shard="s1"):
        self.serial += 1
        relative = f"reports/result-{self.serial}.xml"
        path = self.base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"path": relative, "shard": shard}

    def run_record(self, identifier, cases=None, **changes):
        run = {
            "id": identifier, "commit": "abcdef1234567", "branch": "main",
            "workflow": "unit", "environment": "linux-python3",
            "started_at": "2026-09-08T12:00:00Z", "expected_shards": ["s1"],
            "reports": [self.report(junit([case()] if cases is None else cases))],
        }
        run.update(changes)
        return run

    def write_manifest(self, runs):
        self.manifest.write_text(json.dumps({"schema": 1, "runs": runs}), encoding="utf-8")

    def import_runs(self, runs):
        self.write_manifest(runs)
        return ingest(self.manifest, self.db)

    def by_run(self):
        return {run["id"]: run for run in snapshot(self.db)["runs"]}

    def test_missing_declared_shard_remains_incomplete(self):
        self.import_runs([self.run_record("partial", expected_shards=["s1", "s2"])])
        data = snapshot(self.db)
        run = data["runs"][0]
        self.assertEqual(run["evidence"]["missing_shards"], ["s2"])
        self.assertFalse(run["complete"])
        self.assertEqual(run["counts"]["passed"], 1)
        self.assertEqual(data["summary"]["incomplete_runs"], 1)
        self.assertTrue(any("Missing declared shards" in message for message in run["warnings"]))

    def test_empty_report_is_not_a_passing_run(self):
        self.import_runs([self.run_record("empty", cases=[])])
        data = snapshot(self.db)
        self.assertEqual(data["summary"]["observations"], 0)
        self.assertFalse(data["runs"][0]["complete"])
        self.assertEqual(data["runs"][0]["counts"]["passed"], 0)
        self.assertTrue(data["runs"][0]["warnings"])

    def test_declared_test_count_mismatch_is_reported_as_incomplete(self):
        xml = b'<testsuite name="suite" tests="5"><testcase classname="C" name="one"/></testsuite>'
        self.import_runs([self.run_record("truncated-count", reports=[self.report(xml)])])
        run = snapshot(self.db)["runs"][0]
        self.assertEqual(run["observations"], 1)
        self.assertEqual(run["counts"]["passed"], 1)
        self.assertFalse(run["complete"])
        self.assertTrue(any("declared test count" in warning for warning in run["warnings"]))

    def test_duplicate_identities_are_preserved_but_excluded_from_comparisons(self):
        reports = [self.report(junit([case(status="passed")], suite="shard-one"), "s1"),
                   self.report(junit([case(status="failed")], suite="shard-two"), "s2")]
        run = self.run_record("duplicate", expected_shards=["s1", "s2"], reports=reports)
        later = self.run_record("later", cases=[case(status="failed")],
                                started_at="2026-09-08T13:00:00Z")
        self.import_runs([run, later])
        data = snapshot(self.db)
        self.assertEqual(data["summary"]["observations"], 3)
        self.assertEqual(data["summary"]["tests"], 1)
        duplicate = self.by_run()["duplicate"]
        self.assertEqual(duplicate["counts"]["ambiguous"], 2)
        self.assertFalse(duplicate["complete"])
        self.assertEqual(data["mixed_outcomes"], [])
        self.assertEqual(self.by_run()["later"]["comparison"]["new_failures"], [])
        self.assertEqual(data["tests"][0]["observed"], 1)

    def test_identity_survives_shard_filename_and_suite_label_changes(self):
        first = self.run_record("first", reports=[self.report(junit([case()], suite="shard-1"), "old")],
                                expected_shards=["old"])
        second = self.run_record("second", reports=[self.report(junit([case(status="failed")], suite="shard-7"), "new")],
                                 expected_shards=["new"], started_at="2026-09-08T13:00:00Z")
        self.import_runs([first, second])
        data = snapshot(self.db)
        self.assertEqual(data["summary"]["tests"], 1)
        self.assertEqual(len(self.by_run()["second"]["comparison"]["new_failures"]), 1)

    def test_first_seen_failure_is_not_a_pass_to_fail_transition(self):
        first = self.run_record("first", [case("already_broken", "failed")])
        second = self.run_record("second", [case("already_broken", "failed"), case("new_broken", "failed")],
                                 started_at="2026-09-08T13:00:00Z")
        self.import_runs([first, second])
        data = snapshot(self.db)
        self.assertEqual(data["summary"]["new_failure_events"], 0)
        self.assertEqual(data["summary"]["tests"], 2)
        self.assertTrue(all(not run["comparison"]["new_failures"] for run in data["runs"]))

    def test_pass_fail_and_resolution_have_a_specific_baseline(self):
        rows = [self.run_record("pass", [case()], started_at="2026-09-08T10:00:00Z"),
                self.run_record("fail", [case(status="failed")], started_at="2026-09-08T11:00:00Z"),
                self.run_record("fixed", [case()], started_at="2026-09-08T12:00:00Z")]
        self.import_runs(rows)
        runs = self.by_run()
        self.assertEqual(runs["fail"]["comparison"]["baseline"], "pass")
        self.assertEqual(len(runs["fail"]["comparison"]["new_failures"]), 1)
        self.assertEqual(runs["fixed"]["comparison"]["baseline"], "fail")
        self.assertEqual(len(runs["fixed"]["comparison"]["resolved"]), 1)

    def test_mixed_outcomes_require_matching_commit_and_context(self):
        for different in ({}, {"commit": "1234567abcdef"}, {"environment": "windows"},
                          {"workflow": "integration"}, {"branch": "feature"}):
            with self.subTest(different=different):
                db = self.base / (f"context-{self.serial}.sqlite3")
                first = self.run_record("pass", [case()])
                later = self.run_record("fail", [case(status="failed")],
                                       started_at="2026-09-08T13:00:00Z", **different)
                self.write_manifest([first, later])
                ingest(self.manifest, db)
                result = snapshot(db)
                self.assertEqual(len(result["mixed_outcomes"]), 0 if different else 1)
                if not different:
                    mixed = result["mixed_outcomes"][0]
                    self.assertEqual((mixed["passed"], mixed["failed"]), (1, 1))
                    self.assertEqual(set(mixed["runs"]), {"pass", "fail"})
                if set(different) & {"workflow", "environment", "branch"}:
                    self.assertIsNone(result["runs"][1]["comparison"]["baseline"])

    def test_skipped_missing_and_unknown_observations_are_not_passes(self):
        for middle_cases in ([case(status="skipped")], [case("another_test")],
                             [case(status="flakyFailure")]):
            with self.subTest(middle=middle_cases):
                db = self.base / f"absence-{self.serial}.sqlite3"
                first = self.run_record("first", [case(status="failed")], started_at="2026-09-08T10:00:00Z")
                middle = self.run_record("middle", middle_cases, started_at="2026-09-08T11:00:00Z")
                last = self.run_record("last", [case(status="failed")], started_at="2026-09-08T12:00:00Z")
                self.write_manifest([first, middle, last])
                ingest(self.manifest, db)
                data = snapshot(db)
                self.assertEqual(data["summary"]["new_failure_events"], 0)
                self.assertEqual(data["mixed_outcomes"], [])
                self.assertTrue(all(not run["comparison"]["resolved"] for run in data["runs"]))

    def test_idempotent_reimport_does_not_collapse_distinct_runs(self):
        first = self.run_record("first")
        inserted = self.import_runs([first])
        unchanged = ingest(self.manifest, self.db)
        self.assertEqual(inserted["inserted"], 1)
        self.assertEqual((unchanged["inserted"], unchanged["unchanged"]), (0, 1))
        second = copy.deepcopy(first)
        second.update(id="second", started_at="2026-09-08T13:00:00Z")
        self.import_runs([second])
        data = snapshot(self.db)
        self.assertEqual(data["summary"]["runs"], 2)
        self.assertEqual(data["summary"]["observations"], 2)
        self.assertEqual(data["tests"][0]["observed"], 2)

    def test_conflicting_run_rolls_back_other_new_runs_in_same_import(self):
        original = self.run_record("existing")
        self.import_runs([original])
        before = snapshot(self.db)
        conflict = copy.deepcopy(original)
        conflict["branch"] = "changed-metadata"
        self.write_manifest([self.run_record("new"), conflict])
        with self.assertRaises(ValueError):
            ingest(self.manifest, self.db)
        self.assertEqual(snapshot(self.db), before)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_changed_artifact_conflicts_and_preserves_original_observation(self):
        original = self.run_record("existing")
        self.import_runs([original])
        before = snapshot(self.db)
        (self.base / original["reports"][0]["path"]).write_bytes(junit([case(status="failed")]))
        with self.assertRaises(ValueError):
            ingest(self.manifest, self.db)
        self.assertEqual(snapshot(self.db), before)

    def test_parse_failure_prevents_any_new_runs_being_imported(self):
        self.import_runs([self.run_record("existing")])
        before = snapshot(self.db)
        broken = self.run_record("bad", reports=[self.report(b"<testsuite><testcase")])
        self.write_manifest([self.run_record("new"), broken])
        with self.assertRaises(ValueError):
            ingest(self.manifest, self.db)
        self.assertEqual(snapshot(self.db), before)

    def test_dtd_entities_bad_xml_and_wrong_roots_are_rejected(self):
        invalid = [
            b'<!DOCTYPE testsuite [<!ENTITY injected "payload">]><testsuite/>',
            b'<!DOCTYPE testsuite SYSTEM "file:///does-not-exist"><testsuite/>',
            b"<testsuite><testcase></testsuite>", b"<report><testcase name='x'/></report>",
            "<testsuite/>".encode("utf-16"),
        ]
        for data in invalid:
            with self.subTest(data=data[:60]):
                self.write_manifest([self.run_record("bad", reports=[self.report(data)])])
                with self.assertRaises((ValueError, UnicodeError)):
                    ingest(self.manifest, self.db)
                self.assertFalse(self.db.exists())

    def test_json_duplicates_nonfinite_values_and_wrong_schema_types_are_rejected(self):
        run = self.run_record("one")
        valid = json.dumps({"schema": 1, "runs": [run]}, separators=(",", ":"))
        bad = [valid.replace('"schema":1', '"schema":1,"schema":1', 1),
               valid.replace('"schema":1', '"schema":NaN', 1),
               valid.replace('"schema":1', '"schema":true', 1),
               valid.replace('"schema":1', '"schema":1.0', 1),
               valid[:-1], '{"schema":1,"runs":[]}']
        for raw in bad:
            with self.subTest(raw=raw[:75]):
                self.manifest.write_text(raw)
                with self.assertRaises(ValueError):
                    ingest(self.manifest, self.db)
                self.assertFalse(self.db.exists())

    def test_manifest_metadata_requires_timezone_and_consistent_shards(self):
        changes = [{"started_at": "2026-09-08T12:00:00"}, {"commit": "branch-name"},
                   {"id": "bad\nname"}, {"expected_shards": ["s1", "s1"]},
                   {"expected_shards": ["other"]}, {"reports": []}, {"environment": ""}]
        for change in changes:
            with self.subTest(change=change):
                self.write_manifest([self.run_record("bad", **change)])
                with self.assertRaises(ValueError):
                    ingest(self.manifest, self.db)
                self.assertFalse(self.db.exists())

    def test_traversal_absolute_backslash_symlink_and_duplicate_paths_are_rejected(self):
        outside = self.base.parent / (self.base.name + "-outside.xml")
        outside.write_bytes(junit([case()]))
        self.addCleanup(outside.unlink)
        symlink = self.base / "linked.xml"
        symlink.symlink_to(outside)
        entries = [{"path": str(outside), "shard": "s1"},
                   {"path": "../" + outside.name, "shard": "s1"},
                   {"path": "..\\outside.xml", "shard": "s1"},
                   {"path": "linked.xml", "shard": "s1"}]
        for entry in entries:
            with self.subTest(entry=entry):
                self.write_manifest([self.run_record("bad", reports=[entry])])
                with self.assertRaises(ValueError):
                    ingest(self.manifest, self.db)
                self.assertFalse(self.db.exists())
        entry = self.report(junit([case()]))
        duplicate = {**entry, "path": "./" + entry["path"]}
        self.write_manifest([self.run_record("bad", reports=[entry, duplicate])])
        with self.assertRaises(ValueError):
            ingest(self.manifest, self.db)

    def test_history_order_uses_normalized_timestamp_not_import_order(self):
        late = self.run_record("late", [case(status="failed")], started_at="2026-09-08T09:00:00-04:00")
        early = self.run_record("early", [case()], started_at="2026-09-08T12:00:00Z")
        self.import_runs([late])
        self.import_runs([early])
        data = snapshot(self.db)
        self.assertEqual([r["id"] for r in data["runs"]], ["early", "late"])
        self.assertEqual(data["runs"][1]["started_at"], "2026-09-08T13:00:00+00:00")
        self.assertEqual(data["runs"][1]["comparison"]["baseline"], "early")
        self.assertEqual(len(data["runs"][1]["comparison"]["new_failures"]), 1)

    def test_equal_timestamp_conflicts_do_not_supply_an_arbitrary_later_baseline(self):
        # Sorting tied runs by ID is display order, not chronological evidence.
        rows = [self.run_record("a_failed", [case(status="failed")]),
                self.run_record("z_passed", [case()]),
                self.run_record("later_failed", [case(status="failed")],
                                started_at="2026-09-08T13:00:00Z")]
        self.import_runs(rows)
        runs = self.by_run()
        self.assertEqual(runs["later_failed"]["comparison"]["new_failures"], [])
        self.assertIsNone(runs["later_failed"]["comparison"]["baseline"])

    def test_invalid_and_missing_durations_do_not_become_zero_or_slowdowns(self):
        values = (None, "nan", "inf", "-1", "bad", "1e309")
        rows = [case(f"test_{i}", time=value) for i, value in enumerate(values)]
        rows.append(case("zero_is_valid", time="0"))
        self.import_runs([self.run_record("timing", rows)])
        data = snapshot(self.db)
        tests = {t["name"]: t for t in data["tests"]}
        for i, _ in enumerate(values):
            self.assertIsNone(tests[f"test_{i}"]["history"][0]["duration"])
            self.assertIsNone(tests[f"test_{i}"]["median_seconds"])
        self.assertEqual(tests["zero_is_valid"]["history"][0]["duration"], 0)
        self.assertEqual(data["runs"][0]["test_seconds"], 0)
        self.assertEqual(data["runs"][0]["comparison"]["slowdowns"], [])
        self.assertGreaterEqual(len(data["runs"][0]["warnings"]), 5)

    def test_slowdown_rule_compares_passing_observations_with_known_positive_baseline(self):
        first_cases = [case("slow", time="1"), case("small_delta", time="0.01"),
                       case("failed_before", status="failed", time="1"),
                       case("unknown_before", time=None), case("zero_before", time="0")]
        later_cases = [case("slow", time="2.5"), case("small_delta", time="0.03"),
                       case("failed_before", time="5"), case("unknown_before", time="5"),
                       case("zero_before", time="5")]
        self.import_runs([self.run_record("first", first_cases),
                          self.run_record("later", later_cases, started_at="2026-09-08T13:00:00Z")])
        data = snapshot(self.db)
        later = self.by_run()["later"]
        slowdowns = later["comparison"]["slowdowns"]
        self.assertEqual(len(slowdowns), 1)
        slow_id = next(t["id"] for t in data["tests"] if t["name"] == "slow")
        self.assertEqual(slowdowns[0], {"test_id": slow_id, "before": 1.0, "after": 2.5, "ratio": 2.5})
        self.assertAlmostEqual(later["test_seconds"], 17.53)

    def test_namespaced_basic_junit_and_unknown_result_extensions(self):
        xml = b'''<testsuites xmlns="urn:synthetic:junit"><testsuite name="suite">
          <testcase classname="C" name="plain"/>
          <testcase classname="C" name="unsupported-status" status="notrun"/>
          <testcase classname="C" name="retry"><flakyFailure/></testcase>
          <testcase classname="C" name="conflict"><failure/><skipped/></testcase>
          <testcase classname="C" name="error"><error/></testcase>
        </testsuite></testsuites>'''
        self.import_runs([self.run_record("dialect", reports=[self.report(xml)])])
        data = snapshot(self.db)
        run = data["runs"][0]
        self.assertEqual((run["counts"]["passed"], run["counts"]["failed"], run["counts"]["unknown"]), (1, 1, 3))
        self.assertFalse(run["complete"])
        self.assertEqual(sum(t["observed"] for t in data["tests"]), 2)

    def test_hash_provenance_retained_without_persisting_failure_messages_or_logs(self):
        marker = "SYNTHETIC_PRIVATE_LOG_SENTINEL_12345"
        xml = f'''<testsuite name="suite"><testcase name="t" classname="C">
          <failure message="{marker}">{marker}</failure>
          <system-out>{marker}</system-out><system-err>{marker}</system-err>
        </testcase></testsuite>'''.encode()
        report = self.report(xml)
        self.import_runs([self.run_record("provenance", reports=[report])])
        data = snapshot(self.db)
        source = data["runs"][0]["evidence"]["files"][0]
        self.assertEqual(source["sha256"], hashlib.sha256(xml).hexdigest())
        self.assertEqual(source["bytes"], len(xml))
        self.assertEqual(source["path"], report["path"])
        self.assertEqual(data["runs"][0]["evidence"]["parser_version"], ingest_module.__version__)
        self.assertNotIn(marker, json.dumps(data))
        self.assertNotIn(marker.encode(), self.db.read_bytes())

    def test_changed_parser_version_cannot_silently_reuse_old_run_evidence(self):
        self.import_runs([self.run_record("existing")])
        before = snapshot(self.db)
        with patch.object(ingest_module, "__version__", "synthetic-different-parser"):
            with self.assertRaises(ValueError):
                ingest(self.manifest, self.db)
        self.assertEqual(snapshot(self.db), before)

    def test_input_resource_limits_are_enforced_before_import(self):
        run = self.run_record("large", [case("a"), case("b")])
        self.write_manifest([run])
        with patch.object(ingest_module, "MAX_CASES", 1):
            with self.assertRaises(ValueError):
                ingest(self.manifest, self.db)
        with patch.object(ingest_module, "MAX_XML", 32):
            with self.assertRaises(ValueError):
                ingest(self.manifest, self.db)
        with patch.object(ingest_module, "MAX_MANIFEST", 32):
            with self.assertRaises(ValueError):
                ingest(self.manifest, self.db)
        self.assertFalse(self.db.exists())

    def test_readonly_snapshot_does_not_create_a_missing_database(self):
        with self.assertRaises(sqlite3.Error):
            snapshot(self.db)
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
