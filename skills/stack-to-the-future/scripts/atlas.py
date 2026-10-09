#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tree-sitter>=0.25,<0.26", "tree-sitter-python>=0.25", "tree-sitter-typescript>=0.23.2", "networkx>=3.3", "jsonschema>=4.23"]
# ///
# ponytail: tree-sitter 0.26.0 segfaults walking some real files (repro: full-stack-fastapi-template
# backend/tests/api/routes/test_users.py); 0.25.2 is fine. Lift the cap once a fixed 0.26.x is out.
"""Stack to the Future command line. Everything here is deterministic; Claude does the naming."""
import argparse
import json
import sys
from pathlib import Path

import cluster
import scan

ATLAS_GITIGNORE = "scan.json\ndraft.json\ncache/\n"


def cmd_scan(args) -> None:
    root = Path(args.root).resolve()
    out = root / ".atlas"
    out.mkdir(exist_ok=True)
    if not (out / ".gitignore").exists():
        (out / ".gitignore").write_text(ATLAS_GITIGNORE)
    result = scan.scan(root)
    result["clusters"] = cluster.cluster(result, args.draft_limit)
    (out / "scan.json").write_text(json.dumps(result, indent=2) + "\n")

    c = result["clusters"]
    kinds = {}
    for e in result["entry_points"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print(f"Scanned {len(result['files'])} files -> {out / 'scan.json'}")
    print(f"  entry points: {', '.join(f'{n} {k}' for k, n in sorted(kinds.items())) or 'none'}")
    print(f"  status machines: {len(result['status_machines'])}, permission branches: {len(result['permission_branches'])}, "
          f"models: {len(result['models'])}, incomplete: {len(result['incomplete'])}")
    for m in c["modules"]:
        print(f"  module {m['id']} ({m['role']}): {len(m['files'])} files, {len(m['workflows'])} workflow skeletons")
    if result["redactions"]:
        print(f"  redacted {result['redactions']} secret value(s)")


def cmd_validate(args) -> None:
    import validate

    root = Path(args.root).resolve()
    scan_path = root / ".atlas" / "scan.json"
    if not scan_path.exists():
        sys.exit(f"No {scan_path}; run `atlas.py scan {root}` first.")
    errors = validate.validate(json.loads(Path(args.draft).read_text()), json.loads(scan_path.read_text()))
    print(validate.report(errors))
    if errors:
        sys.exit(1)


def cmd_excerpt(args) -> None:
    from redact import is_secret_file, redact

    root = Path(args.root).resolve()
    target = (root / args.path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        sys.exit(f"{args.path} is not a file inside {root}")
    if is_secret_file(args.path):
        sys.exit(f"{args.path} is a secrets file; it is never read.")
    lines = redact(target.read_text(errors="replace"))[0].splitlines()
    start, end = max(args.start, 1), min(args.end, len(lines))
    width = len(str(end))
    for n in range(start, end + 1):
        print(f"{n:>{width}} | {lines[n - 1]}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="atlas.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan", help="static scan and clustering, writes .atlas/scan.json")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--draft-limit", type=int, default=8, help="modules to draft now; the rest are listed as not yet drawn")
    p.set_defaults(func=cmd_scan)
    p = sub.add_parser("validate", help="check a drafted atlas against the schema and .atlas/scan.json")
    p.add_argument("draft")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser("excerpt", help="print redacted source lines with line numbers")
    p.add_argument("path")
    p.add_argument("start", type=int)
    p.add_argument("end", type=int)
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_excerpt)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
