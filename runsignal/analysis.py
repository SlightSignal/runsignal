"""Descriptive comparisons only; no claim to infer root causes or future failures."""
from collections import defaultdict
import json
from pathlib import Path
import sqlite3
import statistics


def snapshot(database):
    uri = Path(database).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    try:
        version = db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()
        if not version or version[0] != "1":
            raise ValueError("Unsupported database schema")
        runs = [dict(r) for r in db.execute("SELECT * FROM runs ORDER BY started_at,id")]
        observations = [dict(r) for r in db.execute("SELECT * FROM observations ORDER BY run_id,ordinal")]
    finally:
        db.close()
    by_run = defaultdict(list)
    for row in observations:
        by_run[row["run_id"]].append(row)
    groups, tests = {}, {}
    mixed_buckets = defaultdict(list)
    for run in runs:
        run["warnings"] = json.loads(run.pop("warning_json"))
        run["evidence"] = json.loads(run.pop("report_json"))
        run_rows = by_run[run["id"]]
        counts = {k: sum(r["status"] == k for r in run_rows) for k in ("passed", "failed", "skipped", "unknown")}
        counts["ambiguous"] = sum(r["ambiguous"] for r in run_rows)
        run["counts"] = counts
        run["observations"] = len(run_rows)
        run["complete"] = bool(run_rows) and not (counts["ambiguous"] or counts["unknown"] or run["evidence"]["missing_shards"] or run["warnings"])
        # Sum is test execution effort, not elapsed CI wall time.
        run["test_seconds"] = round(sum(r["duration"] for r in run_rows if r["duration"] is not None), 3)
        group = (run["workflow"], run["environment"], run["branch"])
        gids = json.dumps(group, separators=(",", ":"))
        run["group"] = gids
        previous = groups.get(gids)
        current = {r["test_id"]: r for r in run_rows if not r["ambiguous"] and r["status"] in {"passed", "failed"}}
        prior = previous["rows"] if previous else {}
        # Equal timestamps do not establish run order. Suppress that comparison.
        comparable = bool(previous) and not previous["tied"] and run["started_at"] > previous["run"]["started_at"]
        new_failures, resolved, slowdowns = [], [], []
        if comparable:
            for tid in current.keys() & prior.keys():
                row, old = current[tid], prior[tid]
                if row["status"] == "failed" and old["status"] == "passed":
                    new_failures.append(tid)
                if row["status"] == "passed" and old["status"] == "failed":
                    resolved.append(tid)
                before, after = old["duration"], row["duration"]
                if (old["status"] == row["status"] == "passed" and before is not None
                        and after is not None and before > 0 and after >= before * 2 and after - before >= 0.1):
                    slowdowns.append({"test_id": tid, "before": before, "after": after, "ratio": round(after / before, 2)})
        run["comparison"] = {"baseline": previous["run"]["id"] if comparable else None,
                             "new_failures": sorted(new_failures), "resolved": sorted(resolved),
                             "slowdowns": sorted(slowdowns, key=lambda x: x["test_id"]),
                             "not_comparable": len(run_rows) - len(current.keys() & prior.keys()) if comparable else len(run_rows)}
        groups[gids] = {"run": run, "rows": current,
                       "tied": bool(previous) and run["started_at"] == previous["run"]["started_at"]}
        for row in run_rows:
            tid = row["test_id"]
            test = tests.setdefault(tid, {"id": tid, "name": row["name"], "classname": row["classname"],
                                         "file": row["file"], "history": []})
            entry = {"run_id": run["id"], "commit": run["commit_sha"], "environment": run["environment"],
                     "workflow": run["workflow"], "branch": run["branch"], "started_at": run["started_at"],
                     "status": row["status"], "duration": row["duration"], "ambiguous": bool(row["ambiguous"]),
                     "report": row["report"], "shard": row["shard"], "group": gids}
            test["history"].append(entry)
            if not row["ambiguous"] and row["status"] in {"passed", "failed"}:
                mixed_buckets[(tid, run["commit_sha"], run["workflow"], run["environment"], run["branch"])].append(entry)
    mixed = []
    for (tid, commit, workflow, environment, branch), entries in mixed_buckets.items():
        if {e["status"] for e in entries} == {"passed", "failed"}:
            mixed.append({"test_id": tid, "commit": commit, "workflow": workflow, "environment": environment,
                          "branch": branch, "runs": [e["run_id"] for e in entries],
                          "passed": sum(e["status"] == "passed" for e in entries),
                          "failed": sum(e["status"] == "failed" for e in entries)})
    for test in tests.values():
        valid = [e for e in test["history"] if not e["ambiguous"] and e["status"] in {"passed", "failed"}]
        test["observed"] = len(valid)
        test["failures"] = sum(e["status"] == "failed" for e in valid)
        test["failure_rate"] = round(test["failures"] / len(valid), 4) if valid else None
        durations = [e["duration"] for e in valid if e["duration"] is not None]
        test["median_seconds"] = round(statistics.median(durations), 4) if durations else None
        test["mixed_groups"] = sum(m["test_id"] == test["id"] for m in mixed)
    ordered = sorted(tests.values(), key=lambda t: (-t["mixed_groups"], -t["failures"], t["name"], t["id"]))
    return {"schema": 1, "runs": runs, "tests": ordered, "mixed_outcomes": sorted(mixed, key=lambda m: (m["test_id"], m["commit"])),
            "summary": {"runs": len(runs), "tests": len(tests), "observations": len(observations),
                        "mixed_tests": len({m["test_id"] for m in mixed}),
                        "incomplete_runs": sum(not r["complete"] for r in runs),
                        "new_failure_events": sum(len(r["comparison"]["new_failures"]) for r in runs)}}
