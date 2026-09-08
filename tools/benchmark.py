"""Synthetic scale/correctness check, not a competitor or real-CI benchmark."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import platform
import resource
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runsignal.ingest import ingest
from runsignal.analysis import snapshot
from runsignal.report import render


def main():
    with tempfile.TemporaryDirectory(prefix="runsignal-benchmark-") as folder:
        base = Path(folder)
        runs = []
        started = datetime(2026, 1, 1, tzinfo=timezone.utc)
        total_bytes = 0
        for i in range(100):
            reports = []
            for s in range(2):
                if i == 90 and s == 1:
                    continue
                suite = ET.Element("testsuite", name=f"shard-{s}")
                for n in range(s, 500, 2):
                    case = ET.SubElement(suite, "testcase", name=f"test_{n}", classname="synthetic.catalog", file=f"tests/test_{n}.py", time="0.8" if n == 2 and i >= 70 else "0.2")
                    if (n == 0 and i % 2 == 1) or (n == 1 and i >= 50):
                        ET.SubElement(case, "failure")
                    if n == 3 and i == 20:
                        duplicate = ET.SubElement(suite, "testcase", name=f"test_{n}", classname="synthetic.catalog", file=f"tests/test_{n}.py", time="0.2")
                        ET.SubElement(duplicate, "failure")
                path = f"run-{i}-shard-{s}.xml"
                data = ET.tostring(suite, encoding="utf-8")
                total_bytes += len(data)
                (base / path).write_bytes(data)
                reports.append({"path":path, "shard":str(s)})
            runs.append({"id":f"scale-{i:03d}","commit":f"{i//2+100:040x}","branch":"main","workflow":"synthetic-scale","environment":"controlled-label",
                         "started_at":(started+timedelta(hours=i)).isoformat(),"expected_shards":["0","1"],"reports":reports})
        path = base / "manifest.json"
        path.write_text(json.dumps({"schema":1,"runs":runs}))
        db = base / "history.sqlite3"
        t0 = time.perf_counter()
        imported = ingest(path, db)
        t1 = time.perf_counter()
        data = snapshot(db)
        t2 = time.perf_counter()
        output = render(data)
        t3 = time.perf_counter()
        expected = {"runs":100,"tests":500,"observations":49751,"mixed_tests":1,"incomplete_runs":2,"new_failure_events":51}
        assert data["summary"] == expected, (data["summary"],expected)
        assert sum(len(r["comparison"]["slowdowns"]) for r in data["runs"]) == 1
        repeat = ingest(path, db)
        assert repeat["inserted"] == 0 and repeat["unchanged"] == 100
        evidence = {"fixture":"100 runs x 500 logical tests, one missing half-shard and one duplicate", "synthetic":True,
                    "expected":expected,"observed":data["summary"],"slowdown_events":1,"reimport_unchanged":repeat["unchanged"],
                    "xml_bytes":total_bytes,"database_bytes":db.stat().st_size,"html_bytes":len(output.encode()),
                    "seconds":{"ingest":round(t1-t0,4),"analysis":round(t2-t1,4),"html_serialization":round(t3-t2,4)},
                    "process_peak_rss_kib_linux":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    "python":platform.python_version(),"platform":platform.system(),
                    "limits":"One synthetic local run; includes fixture memory. No browser performance, sustained-load, competitor or user-productivity benchmark."}
        return evidence


if __name__ == "__main__":
    result = main()
    out = Path(sys.argv[1] if len(sys.argv)>1 else "docs/benchmark.json")
    out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
