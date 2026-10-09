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
        (out / ".gitignore").write_text(ATLAS_GITIGNORE, encoding="utf-8", newline="\n")
    result = scan.scan(root, out / "cache")
    result["clusters"] = cluster.cluster(result, args.draft_limit)
    (out / "scan.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")

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
    errors = validate.validate(json.loads(Path(args.draft).read_text(encoding="utf-8")), json.loads(scan_path.read_text(encoding="utf-8")))
    print(validate.report(errors))
    if errors:
        sys.exit(1)


def cmd_excerpt(args) -> None:
    from redact import read_redacted

    try:
        lines = read_redacted(args.root, args.path)
    except ValueError as e:
        sys.exit(str(e))
    start, end = max(args.start, 1), min(args.end, len(lines))
    width = len(str(end))
    for n in range(start, end + 1):
        print(f"{n:>{width}} | {lines[n - 1]}")


def cmd_walkthrough_context(args) -> None:
    import walkthrough

    root = Path(args.root).resolve()
    if not (root / ".atlas" / "scan.json").exists():
        sys.exit(f"No {root / '.atlas' / 'scan.json'}; run `atlas.py scan {root}` first.")
    try:
        print(walkthrough.context(root, args.path), end="")
    except ValueError as e:
        sys.exit(str(e))


def cmd_check_walkthrough(args) -> None:
    import validate
    import walkthrough

    root = Path(args.root).resolve()
    scan_path = root / ".atlas" / "scan.json"
    if not scan_path.exists():
        sys.exit(f"No {scan_path}; run `atlas.py scan {root}` first.")
    errors = walkthrough.check(Path(args.walkthrough).read_text(encoding="utf-8"), json.loads(scan_path.read_text(encoding="utf-8")))
    print(validate.report(errors))
    if errors:
        sys.exit(1)


def _load(path: Path, hint: str) -> dict:
    if not path.exists():
        sys.exit(f"No {path}; {hint}")
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_merge(args) -> None:
    import checkpoint
    import validate

    atlas_dir = Path(args.root).resolve() / ".atlas"
    scan_ = _load(atlas_dir / "scan.json", "run `atlas.py scan` first.")
    previous = json.loads((atlas_dir / "atlas.json").read_text(encoding="utf-8")) if (atlas_dir / "atlas.json").exists() else None
    merged = checkpoint.merge(previous, _load(Path(args.draft), "nothing to merge."), scan_)
    if not args.approve:
        (atlas_dir / "draft.json").write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(checkpoint.outline(merged))
        return
    errors = validate.validate(merged, scan_)
    if errors:
        print(validate.report(errors))
        sys.exit(1)
    (atlas_dir / "atlas.json").write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Approved -> {atlas_dir / 'atlas.json'}")


def cmd_stale(args) -> None:
    import checkpoint

    atlas_dir = Path(args.root).resolve() / ".atlas"
    redraft, review = checkpoint.stale(_load(atlas_dir / "atlas.json", "no approved atlas yet; draft one first."),
                                       _load(atlas_dir / "scan.json", "run `atlas.py scan` first."))
    if not redraft and not review:
        print("Nothing changed since the atlas was approved.")
    for title, items in ((f"Re-draft ({len(redraft)}):", redraft), (f"Needs human review, locked by you ({len(review)}):", review)):
        if items:
            print(title, *(f"  - {i}" for i in items), sep="\n")


def cmd_outline(args) -> None:
    import checkpoint

    atlas_dir = Path(args.root).resolve() / ".atlas"
    print(checkpoint.outline(_load(atlas_dir / ("draft.json" if args.draft else "atlas.json"), "nothing to outline yet.")))


def cmd_render(args) -> None:
    from render import excalidraw, html, lal

    renderers = {"html": html.render, "excalidraw": excalidraw.render, "lal": lal.render}
    formats = [f.strip() for f in args.format.split(",") if f.strip()]
    unknown = set(formats) - set(renderers)
    if unknown:
        raise SystemExit(f"unknown format(s): {', '.join(sorted(unknown))}; choose from {', '.join(renderers)}")
    atlas_dir = Path(args.root).resolve() / ".atlas"
    data = _load(atlas_dir / "atlas.json", "approve an atlas first: `atlas.py merge <draft> --approve`.")
    out = atlas_dir / "out"
    out.mkdir(exist_ok=True)
    rendered = {f: renderers[f](data) for f in formats}  # all or nothing: any secret hit raises before a file is written
    for fmt, text in rendered.items():
        (out / f"atlas.{fmt}").write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote {out / f'atlas.{fmt}'}")


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
    p = sub.add_parser("walkthrough-context", help="everything known about one file, for writing its walkthrough")
    p.add_argument("path")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_walkthrough_context)
    p = sub.add_parser("check-walkthrough", help="check a walkthrough's citations, steps and redaction")
    p.add_argument("walkthrough")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_check_walkthrough)
    p = sub.add_parser("merge", help="merge a draft with locked corrections; --approve validates and writes atlas.json")
    p.add_argument("draft")
    p.add_argument("--root", default=".")
    p.add_argument("--approve", action="store_true")
    p.set_defaults(func=cmd_merge)
    p = sub.add_parser("stale", help="list what a re-scan made stale since atlas.json was approved")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_stale)
    p = sub.add_parser("outline", help="print the checkpoint outline of atlas.json (or draft.json with --draft)")
    p.add_argument("--root", default=".")
    p.add_argument("--draft", action="store_true")
    p.set_defaults(func=cmd_outline)
    p = sub.add_parser("render", help="draw .atlas/atlas.json into .atlas/out/atlas.{html,excalidraw,lal}")
    p.add_argument("--root", default=".")
    p.add_argument("--format", default="lal,excalidraw,html", help="comma-separated: lal, excalidraw, html")
    p.set_defaults(func=cmd_render)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
