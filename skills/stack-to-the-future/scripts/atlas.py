#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tree-sitter>=0.25,<0.26", "tree-sitter-python>=0.25", "networkx>=3.3"]
# ///
# ponytail: tree-sitter 0.26.0 segfaults walking some real files (repro: full-stack-fastapi-template
# backend/tests/api/routes/test_users.py); 0.25.2 is fine. Lift the cap once a fixed 0.26.x is out.
"""Stack to the Future command line. Everything here is deterministic; Claude does the naming."""
import argparse
import json
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


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="atlas.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan", help="static scan and clustering, writes .atlas/scan.json")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--draft-limit", type=int, default=8, help="modules to draft now; the rest are listed as not yet drawn")
    p.set_defaults(func=cmd_scan)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
