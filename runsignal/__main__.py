import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .analysis import snapshot
from .ingest import ingest
from . import __version__


def main():
    parser = argparse.ArgumentParser(description="RunSignal — local JUnit test history and evidence")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    imp = commands.add_parser("ingest", help="Import an explicit run manifest transactionally")
    imp.add_argument("manifest", type=Path)
    imp.add_argument("--db", type=Path, default=Path("runsignal.sqlite3"))
    export = commands.add_parser("report", help="Export an offline HTML dashboard and JSON snapshot")
    export.add_argument("--db", type=Path, default=Path("runsignal.sqlite3"))
    export.add_argument("--out", type=Path, required=True)
    stats = commands.add_parser("summary", help="Print observed test history counts as JSON")
    stats.add_argument("--db", type=Path, default=Path("runsignal.sqlite3"))
    args = parser.parse_args()
    try:
        if args.command == "ingest":
            result = ingest(args.manifest, args.db)
        elif args.command == "summary":
            result = snapshot(args.db)["summary"]
        else:
            from .report import render
            data = snapshot(args.db)
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / "index.html").write_text(render(data), encoding="utf-8")
            (args.out / "report.json").write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            result = {"html": str(args.out / "index.html"), **data["summary"]}
    except (ValueError, OSError, UnicodeError, sqlite3.Error) as exc:
        print(f"RunSignal: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
