"""Strict, transactional ingestion of explicit run manifests and JUnit reports."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import xml.etree.ElementTree as ET
from . import __version__

MAX_XML = 20 * 1024 * 1024
MAX_MANIFEST = 2 * 1024 * 1024
MAX_CASES = 100000
MAX_TOTAL_BYTES = 100 * 1024 * 1024
SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, digest TEXT NOT NULL, commit_sha TEXT NOT NULL,
  branch TEXT NOT NULL, workflow TEXT NOT NULL, environment TEXT NOT NULL,
  started_at TEXT NOT NULL, warning_json TEXT NOT NULL, report_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
  run_id TEXT NOT NULL REFERENCES runs(id), ordinal INTEGER NOT NULL,
  test_id TEXT NOT NULL, suite TEXT NOT NULL, classname TEXT NOT NULL,
  name TEXT NOT NULL, file TEXT NOT NULL, status TEXT NOT NULL,
  duration REAL, shard TEXT NOT NULL, report TEXT NOT NULL,
  ambiguous INTEGER NOT NULL, PRIMARY KEY(run_id, ordinal)
);
CREATE INDEX IF NOT EXISTS observations_test ON observations(test_id, run_id);
"""


def canonical(obj):
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_limited(path, limit):
    with Path(path).open("rb") as f:
        data = f.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Input exceeds {limit} byte limit: {Path(path).name}")
    return data


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(data):
    return json.loads(data, object_pairs_hook=no_duplicate_keys,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def text(value, field, limit=240):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{field}: requires 1–{limit} text characters")
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"{field}: control characters are not supported")
    return value


def tag(element):
    return element.tag.rsplit("}", 1)[-1]


def parse_report(data, report, shard):
    if len(data) > MAX_XML:
        raise ValueError("JUnit report is too large")
    # Support UTF-8 only; do not let UTF-16 evade declaration rejection.
    xml = data.decode("utf-8-sig")
    if "\x00" in xml or re.search(r"<!\s*(DOCTYPE|ENTITY)\b", xml, re.I):
        raise ValueError("DTD/entity declarations and non-UTF-8 XML are not supported")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid JUnit XML in {report}: {exc}") from exc
    if tag(root) not in {"testsuites", "testsuite"}:
        raise ValueError(f"Expected testsuite/testsuites root in {report}")
    rows, warnings = [], []
    descendant_cases = {}
    for node in reversed(list(root.iter())):
        count = 1 if tag(node) == "testcase" else sum(descendant_cases[c] for c in node)
        descendant_cases[node] = count
        if tag(node) in {"testsuite", "testsuites"} and node.get("tests") is not None:
            declared = node.get("tests")
            if not re.fullmatch(r"[0-9]+", declared) or int(declared) != count:
                warnings.append(f"{report}: declared test count differs from parsed testcase count")
    queue = [(root, ())]
    while queue:
        node, parents = queue.pop()
        kind = tag(node)
        if kind == "testsuite":
            suite_name = node.get("name", "")
            parents = (*parents, suite_name)
            if len(parents) > 100:
                raise ValueError("JUnit suite nesting exceeds 100")
        if kind == "testcase":
            if len(rows) >= MAX_CASES:
                raise ValueError("Too many testcases in one report")
            name = text(node.get("name"), "testcase.name", 1000)
            classname = node.get("classname", "")
            filename = node.get("file", "")
            suite = " / ".join(parents)
            for value in (classname, filename, suite):
                if len(value) > 2000 or any(ord(c) < 32 for c in value):
                    raise ValueError("Invalid or oversized testcase identity")
            child_tags = {tag(c) for c in node}
            statuses = child_tags & {"failure", "error", "skipped"}
            unknown = child_tags - {"failure", "error", "skipped", "system-out", "system-err", "properties"}
            nonstandard_status = node.get("status", "").lower() not in {"", "run", "passed"}
            if len(statuses) > 1 or unknown or nonstandard_status:
                status = "unknown"
                warnings.append(f"{report}: unsupported or conflicting result for {name}")
            else:
                status = "failed" if statuses & {"failure", "error"} else "skipped" if statuses else "passed"
            duration = None
            if node.get("time") is not None:
                try:
                    duration = float(node.get("time"))
                    if not math.isfinite(duration) or duration < 0:
                        raise ValueError()
                except (ValueError, OverflowError):
                    warnings.append(f"{report}: invalid duration for {name}; excluded from timing")
                    duration = None
            # Parent suite labels sometimes change per shard. Identity deliberately
            # uses classname+name+file; collisions are retained and made ambiguous.
            test_id = digest(canonical([classname, name, filename]).encode())
            rows.append({"test_id": test_id, "suite": suite, "classname": classname,
                         "name": name, "file": filename, "status": status,
                         "duration": duration, "shard": shard, "report": report,
                         "ambiguous": False})
            continue
        queue.extend((child, parents) for child in reversed(list(node)) if tag(child) in {"testsuites", "testsuite", "testcase"})
    if not rows:
        warnings.append(f"{report}: no testcase observations; this is not a passing test run")
    return rows, warnings


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    version = db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()
    if version and version[0] != "1":
        db.close()
        raise ValueError("Unsupported database schema")
    db.execute("INSERT OR IGNORE INTO metadata VALUES ('schema', '1')")
    db.commit()
    return db


def prepare_manifest(path):
    path = Path(path).resolve()
    obj = parse_json(read_limited(path, MAX_MANIFEST))
    if not isinstance(obj, dict) or set(obj) != {"schema", "runs"} or type(obj["schema"]) is not int or obj["schema"] != 1:
        raise ValueError("Manifest requires schema:1 and runs")
    if not isinstance(obj["runs"], list) or not 1 <= len(obj["runs"]) <= 1000:
        raise ValueError("Manifest requires 1–1000 runs")
    runs, all_bytes, all_cases = [], 0, 0
    for run in obj["runs"]:
        required = {"id", "commit", "branch", "workflow", "environment", "started_at", "reports", "expected_shards"}
        if not isinstance(run, dict) or set(run) != required:
            raise ValueError("Each run requires exactly: " + ", ".join(sorted(required)))
        for field in required - {"reports", "expected_shards"}:
            text(run[field], field)
        expected = run["expected_shards"]
        if not isinstance(expected, list) or not 1 <= len(expected) <= 1000:
            raise ValueError("expected_shards requires 1–1000 shard names")
        expected = [text(x, "expected_shards") for x in expected]
        if len(set(expected)) != len(expected):
            raise ValueError("expected_shards contains duplicates")
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", run["commit"]):
            raise ValueError("commit must be a 7–64 character hexadecimal revision")
        try:
            stamp = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError()
            timestamp = stamp.astimezone(timezone.utc).isoformat()
        except ValueError as exc:
            raise ValueError("started_at must include an ISO-8601 timezone") from exc
        if not isinstance(run["reports"], list) or not 1 <= len(run["reports"]) <= 1000:
            raise ValueError("Each run requires 1–1000 explicit report files")
        rows, warnings, reports, seen = [], [], [], set()
        for entry in run["reports"]:
            if not isinstance(entry, dict) or set(entry) != {"path", "shard"}:
                raise ValueError("Each report requires path and shard")
            relative = text(entry["path"], "report.path", 1000)
            shard = text(entry["shard"], "report.shard")
            if shard not in expected:
                raise ValueError("Report shard is not in expected_shards")
            rp = Path(relative)
            if rp.is_absolute() or ".." in rp.parts or "\\" in relative:
                raise ValueError("Reports must be relative files inside the manifest directory")
            target = path.parent / rp
            if any(p.is_symlink() for p in [target, *target.parents] if p != path.parent):
                raise ValueError("Symlinked reports/directories are unsupported")
            if not target.resolve().is_relative_to(path.parent):
                raise ValueError("Report escapes manifest directory")
            normalized = rp.as_posix()
            if normalized in seen:
                raise ValueError("Same report path listed twice in a run")
            seen.add(normalized)
            data = read_limited(target, MAX_XML)
            all_bytes += len(data)
            if all_bytes > MAX_TOTAL_BYTES:
                raise ValueError("Manifest report total exceeds 100 MiB")
            report_rows, report_warnings = parse_report(data, normalized, shard)
            rows.extend(report_rows)
            warnings.extend(report_warnings)
            reports.append({"path": normalized, "shard": shard, "sha256": digest(data), "bytes": len(data)})
        counts = Counter(r["test_id"] for r in rows)
        for row in rows:
            row["ambiguous"] = counts[row["test_id"]] > 1
        duplicates = sum(n > 1 for n in counts.values())
        if duplicates:
            warnings.append(f"{duplicates} duplicated test identities retained; excluded from comparisons")
        missing = sorted(set(expected) - {r["shard"] for r in reports})
        if missing:
            warnings.append("Missing declared shards: " + ", ".join(missing))
        all_cases += len(rows)
        if all_cases > 500000:
            raise ValueError("Manifest exceeds 500000 observations")
        record = {"id": run["id"], "commit": run["commit"].lower(), "branch": run["branch"],
                  "workflow": run["workflow"], "environment": run["environment"],
                  "started_at": timestamp, "reports": {"files": reports, "expected_shards": sorted(expected), "missing_shards": missing, "parser_version": __version__}}
        runs.append({**record, "digest": digest(canonical(record).encode()), "rows": rows, "warnings": warnings})
    return runs


def ingest(manifest, database):
    # Parse every file before beginning writes: errors never leave half an import.
    runs = prepare_manifest(manifest)
    inserted, unchanged = 0, 0
    db = connect(database)
    try:
        with db:
            for run in runs:
                old = db.execute("SELECT digest FROM runs WHERE id=?", (run["id"],)).fetchone()
                if old:
                    if old[0] != run["digest"]:
                        raise ValueError(f"Run ID already has different evidence: {run['id']}")
                    unchanged += 1
                    continue
                db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?)", (
                    run["id"], run["digest"], run["commit"], run["branch"], run["workflow"],
                    run["environment"], run["started_at"], canonical(run["warnings"]), canonical(run["reports"])))
                for i, row in enumerate(run["rows"]):
                    db.execute("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                        run["id"], i, row["test_id"], row["suite"], row["classname"], row["name"],
                        row["file"], row["status"], row["duration"], row["shard"], row["report"], int(row["ambiguous"])))
                inserted += 1
    finally:
        db.close()
    return {"inserted": inserted, "unchanged": unchanged, "observations_seen": sum(len(r["rows"]) for r in runs)}
