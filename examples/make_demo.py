"""Deterministic synthetic history with planted, documented signals."""
from datetime import datetime, timedelta, timezone
import json
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET


def generate(base):
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    runs = []
    names = ["test_preview_cache", "test_markdown_links", "test_export_archive", "test_thumbnail_index",
             "test_search_filter", "test_manifest_digest", "test_unicode_titles", "test_path_case"]
    names += [f"test_catalog_layout_{i:02d}" for i in range(32)]
    start = datetime(2026, 9, 1, 9, tzinfo=timezone.utc)
    for i in range(24):
        commit = hashlib.sha256(f"synthetic-commit-{i//2}".encode()).hexdigest()[:40]
        reports = []
        for shard in range(4):
            if i == 19 and shard == 3:
                continue
            suite = ET.Element("testsuite", name=f"catalog-shard-{shard}")
            for n, name in enumerate(names):
                if n % 4 != shard:
                    continue
                # One same-commit mixed outcome; another failure persists only
                # across commits and must not automatically be called flaky.
                failed = (n == 0 and i % 6 == 1) or (n == 1 and i >= 20) or (n == 2 and 12 <= i <= 15)
                seconds = round(0.04 + (n % 8) * .09, 3)
                if n == 3 and i >= 18:
                    seconds *= 3.4
                case = ET.SubElement(suite, "testcase", name=name, classname="catalog."+["cache","render","export","index"][shard], file=f"tests/test_{shard}.py", time=str(round(seconds,3)))
                if n == 7 and i == 8:
                    ET.SubElement(case, "skipped", message="Synthetic skip")
                elif failed:
                    ET.SubElement(case, "failure", message="Planted demo failure").text="Synthetic fixture: no production project involved."
            relative = f"reports/run-{i:02d}/shard-{shard}.xml"
            target = base / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(ET.tostring(suite, encoding="utf-8", xml_declaration=True))
            reports.append({"path": relative, "shard": f"shard-{shard}"})
        runs.append({"id":f"demo-{i+1:03d}", "commit":commit, "workflow":"catalog-tests",
                     "branch":"main", "environment":"linux / python-3.12", "started_at":(start+timedelta(hours=i*6)).isoformat(),
                     "expected_shards":[f"shard-{s}" for s in range(4)], "reports":reports})
    path = base / "manifest.json"
    path.write_text(json.dumps({"schema":1,"runs":runs},indent=2)+"\n")
    return path


if __name__ == "__main__":
    print(generate(Path(__file__).parent / "synthetic"))
