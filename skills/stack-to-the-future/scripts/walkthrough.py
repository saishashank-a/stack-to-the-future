"""On-demand file walkthroughs: the context Claude reads before writing one, and the check it must pass after."""
import json
import re
from pathlib import Path

import validate
from redact import read_redacted, redact

# `app/leave/service.py:13-19` or `app/leave/service.py:13-19 choose_route` (single line: `path:13`)
CITATION = re.compile(r"`(?P<path>[\w./-]+\.\w+):(?P<start>\d+)(?:-(?P<end>\d+))?(?:\s+(?P<symbol>[\w.]+))?`")
HEADING = re.compile(r"^(#{1,3})\s+(.*)$")


def context(root: Path, path: str) -> str:
    """Everything known about one file, as plain text for Claude: card, stages, symbols, links, facts, redacted source."""
    root = Path(root).resolve()
    lines = read_redacted(root, path)  # refuses secrets files and paths outside the repo before anything else
    scan = json.loads((root / ".atlas" / "scan.json").read_text(encoding="utf-8"))
    atlas_path = root / ".atlas" / "atlas.json"
    atlas = json.loads(atlas_path.read_text(encoding="utf-8")) if atlas_path.exists() else None
    out = [f"# Walkthrough context: {path}", ""]

    out.append("## Card")
    card = next((c for c in atlas["cards"] if c["file"] == path), None) if atlas else None
    out.append(json.dumps(card, indent=2) if card else "(no card: no atlas.json yet, or this file has none)")

    out += ["", "## Stages this file serves"]
    if atlas:
        for w in atlas["workflows"]:
            for s in w["stages"]:
                for sf in s["files"]:
                    if sf["file"] == path:
                        out.append(f"- {s['id']}: \"{s['name']}\" ({sf['contribution']}; label: {sf.get('label', '-')}) in workflow \"{w['name']}\"")
        for f in atlas["flags"]:
            if f["target"]["id"] == path or any(ev["path"] == path for ev in f["evidence"]):
                out.append(f"- flag {f['id']} ({f['kind']}): {f['message']}")
    else:
        out.append("(no atlas.json yet)")

    out += ["", "## Symbols (name, kind, lines)"]
    out += [f"- {s['name']} ({s['kind']}) {s['start_line']}-{s['end_line']}" for s in scan["symbols"] if s["file"] == path]

    out += ["", "## Called from elsewhere"]
    out += [f"- {c['file']}::{c['caller']} line {c['line']} -> {c['target_symbol']}"
            for c in scan["calls"] if c["target_file"] == path and c["file"] != path] or ["(nothing in the repo)"]
    out += ["", "## Hands off to (calls out of this file)"]
    out += [f"- {c['caller']} line {c['line']} -> {c['target_file']}::{c['target_symbol']}"
            for c in scan["calls"] if c["file"] == path and c["target_file"] != path] or ["(nothing in the repo)"]

    out += ["", "## Facts in this file"]
    for m in scan["status_machines"]:
        for t in m["transitions"]:
            if t["file"] == path:
                out.append(f"- status change: {m['enum']} {'/'.join(t['from']) or '?'} -> {t['to']} in {t['function']} line {t['line']}")
    out += [f"- permission check in {b['function']} line {b['line']}: {b['test']}" for b in scan["permission_branches"] if b["file"] == path]
    out += [f"- incomplete ({i['kind']}) line {i['line']}: {i.get('text') or i.get('symbol')}" for i in scan["incomplete"] if i["file"] == path]
    out += [f"- entry point {e['kind']}: {e['label']} ({e['symbol']})" for e in scan["entry_points"] if e["file"] == path]

    width = len(str(len(lines)))
    out += ["", "## Source (redacted)"] + [f"{n:>{width}} | {text}" for n, text in enumerate(lines, 1)]
    return "\n".join(out) + "\n"


def check(markdown: str, scan: dict) -> list[dict]:
    """Every citation is real, every step cites something, prose stays plain, and nothing secret leaks."""
    errors = []
    scan_files = {f["path"]: f for f in scan["files"]}
    symbols = {(s["file"], s["name"]): s for s in scan["symbols"]}

    for n, text in enumerate(markdown.splitlines(), 1):
        for m in CITATION.finditer(text):
            ev = {"path": m["path"], "start_line": int(m["start"]), "end_line": int(m["end"] or m["start"])}
            if m["symbol"]:
                ev["symbol"] = m["symbol"]
            for rule, message in validate.check_citation(ev, scan_files, symbols):
                errors.append({"where": f"line {n}", "rule": rule, "message": message})
        prose = re.sub(r"`[^`]*`", "", text)
        if code := validate.CODE_LIKE.search(prose):
            errors.append({"where": f"line {n}", "rule": "plain-language",
                           "message": f"'{code.group(0)}' looks like code; put identifiers in backticks or a citation"})

    steps, section, current = [], None, None
    for n, text in enumerate(markdown.splitlines(), 1):
        if h := HEADING.match(text):
            level, title = len(h[1]), h[2].strip()
            if level <= 2:
                section = title.lower()
            current = None
            if level == 3 and section == "step by step":
                current = {"line": n, "title": title, "cited": False}
                steps.append(current)
        elif current and CITATION.search(text):
            current["cited"] = True
    if not steps:
        errors.append({"where": "document", "rule": "steps", "message": "no '### ' steps under '## Step by step'"})
    for s in steps:
        if not s["cited"]:
            errors.append({"where": f"line {s['line']}", "rule": "steps", "message": f"step '{s['title']}' cites no lines"})

    if redact(markdown)[1]:
        errors.append({"where": "document", "rule": "secret", "message": "contains what looks like a secret value; remove it"})
    return errors
