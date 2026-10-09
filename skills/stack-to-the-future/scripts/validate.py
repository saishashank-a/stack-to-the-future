"""Check a drafted atlas against the schema and the deterministic scan (PLAN.md section 2.3).

Every error names where it is (a JSON pointer into the draft) and why, so Claude can fix exactly that item.
"""
import json
import re
from collections import Counter
from pathlib import Path

import jsonschema

from redact import redact

SKILL = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((SKILL / "schema" / "atlas.schema.json").read_text(encoding="utf-8"))
CODE_LIKE = re.compile(r"\w+\.(?:py|tsx?|jsx?|json|toml|ya?ml)\b|\b[a-z]+_\w+|\b[a-z]+[A-Z]\w*|\w\(|::")


def banned_words() -> list[str]:
    """The banned-word list lives in references/plain-language.md; read it from there so there is one copy."""
    text = (SKILL / "references" / "plain-language.md").read_text(encoding="utf-8")
    m = re.search(r"\*\*Banned words[^*]*\*\*\s*(.+)", text)
    return [w.strip(" .") for w in m.group(1).split(",") if w.strip(" .")]


def validate(atlas: dict, scan: dict) -> list[dict]:
    errors = []

    def err(where, rule, message):
        errors.append({"where": where, "rule": rule, "message": message})

    # Rule 0: shape. Later rules assume a well-formed document, so stop here if it isn't.
    for e in sorted(jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker()).iter_errors(atlas),
                    key=lambda e: list(e.absolute_path)):
        err("/" + "/".join(map(str, e.absolute_path)), "schema", e.message)
    if errors:
        return errors

    scan_files = {f["path"]: f for f in scan["files"]}
    symbols = {(s["file"], s["name"]): s for s in scan["symbols"]}

    # The file list is the scan's file list, with the scan's hashes.
    listed = {f["path"]: (i, f) for i, f in enumerate(atlas["files"])}
    for path, (i, f) in listed.items():
        if path not in scan_files:
            err(f"/files/{i}", "files", f"{path} is not in scan.json")
        elif f["sha256"] != scan_files[path]["sha256"]:
            err(f"/files/{i}/sha256", "files", f"{path} changed since it was described; re-scan and redo it")
    for path in sorted(set(scan_files) - set(listed)):
        err("/files", "files", f"{path} was scanned but is missing from files[]")

    # Rules 1 + 2: every citation points at real lines, and a cited symbol exists there.
    for where, ev in evidence(atlas):
        for rule, message in check_citation(ev, scan_files, symbols):
            err(where, rule, message)

    # Rule 3: every reference resolves, and ids are unique.
    modules = {m["id"] for m in atlas["modules"]}
    workflows = {w["id"]: w for w in atlas["workflows"]}
    stages = {s["id"]: (wi, si) for wi, w in enumerate(atlas["workflows"]) for si, s in enumerate(w["stages"])}
    paths = {p["id"] for w in atlas["workflows"] for p in w["paths"]}
    for kind, ids in (("module", [m["id"] for m in atlas["modules"]]), ("workflow", [w["id"] for w in atlas["workflows"]]),
                      ("stage", [s["id"] for w in atlas["workflows"] for s in w["stages"]]),
                      ("path", [p["id"] for w in atlas["workflows"] for p in w["paths"]]),
                      ("variant", [v["id"] for w in atlas["workflows"] for v in w["variants"]]),
                      ("flag", [f["id"] for f in atlas["flags"]])):
        for dup, n in Counter(ids).items():
            if n > 1:
                err("/", "refs", f"{kind} id {dup} is used {n} times")

    def need(where, value, pool, what):
        if value not in pool:
            err(where, "refs", f"{value} is not a known {what}")

    for mi, m in enumerate(atlas["modules"]):
        for j, w in enumerate(m["workflows"]):
            need(f"/modules/{mi}/workflows/{j}", w, workflows, "workflow")
        for j, p in enumerate(m["files"]):
            need(f"/modules/{mi}/files/{j}", p, listed, "file")
    for wi, w in enumerate(atlas["workflows"]):
        base = f"/workflows/{wi}"
        need(f"{base}/module", w["module"], modules, "module")
        own = {s["id"] for s in w["stages"]}
        variants = {v["id"] for v in w["variants"]}
        for si, s in enumerate(w["stages"]):
            for j, sf in enumerate(s["files"]):
                need(f"{base}/stages/{si}/files/{j}/file", sf["file"], listed, "file")
        for pi, p in enumerate(w["paths"]):
            need(f"{base}/paths/{pi}/from", p["from"], own, f"stage of {w['id']}")
            need(f"{base}/paths/{pi}/to", p["to"], own, f"stage of {w['id']}")
            for j, v in enumerate(p.get("variants", [])):
                need(f"{base}/paths/{pi}/variants/{j}", v, variants, f"variant of {w['id']}")
        for vi, v in enumerate(w["variants"]):
            for j, s in enumerate(v["route"]):
                need(f"{base}/variants/{vi}/route/{j}", s, own, f"stage of {w['id']}")
    for li, link in enumerate(atlas.get("links", [])):
        need(f"/links/{li}/from_stage", link["from_stage"], stages, "stage")
        need(f"/links/{li}/to_stage", link["to_stage"], stages, "stage")
    for ci, card in enumerate(atlas["cards"]):
        need(f"/cards/{ci}/file", card["file"], listed, "file")
        for j, s in enumerate(card["stages"]):
            need(f"/cards/{ci}/stages/{j}", s, stages, "stage")
    for xi, sys_ in enumerate(atlas["shared_systems"]):
        for j, p in enumerate(sys_["files"]):
            need(f"/shared_systems/{xi}/files/{j}", p, listed, "file")
        for j, s in enumerate(sys_["used_by_stages"]):
            need(f"/shared_systems/{xi}/used_by_stages/{j}", s, stages, "stage")
    for gi, g in enumerate(atlas["foundation"]):
        for j, p in enumerate(g["files"]):
            need(f"/foundation/{gi}/files/{j}", p, listed, "file")
    targets = {"stage": stages, "path": paths, "file": listed, "workflow": workflows, "module": modules,
               "variant": {v["id"] for w in atlas["workflows"] for v in w["variants"]},
               "shared_system": {s["id"] for s in atlas["shared_systems"]},
               "link": {link_id(link) for link in atlas.get("links", [])}}
    for fi, flag in enumerate(atlas["flags"]):
        need(f"/flags/{fi}/target/id", flag["target"]["id"], targets[flag["target"]["type"]], flag["target"]["type"])

    # Rule 4: business files have exactly one card, foundation files sit in exactly one group.
    cards = Counter(c["file"] for c in atlas["cards"])
    grouped = Counter(p for g in atlas["foundation"] for p in g["files"])
    for path, (i, f) in listed.items():
        want_card, want_group = int(f["layer"] == "business"), int(f["layer"] == "foundation")
        if cards[path] != want_card:
            err(f"/files/{i}", "coverage", f"{path} ({f['layer']}) has {cards[path]} cards, needs {want_card}")
        if grouped[path] != want_group:
            err(f"/files/{i}", "coverage", f"{path} ({f['layer']}) is in {grouped[path]} foundation groups, needs {want_group}")

    on_stages = {}
    for w in atlas["workflows"]:
        for s in w["stages"]:
            for sf in s["files"]:
                on_stages.setdefault(sf["file"], set()).add(s["id"])
    for ci, card in enumerate(atlas["cards"]):
        listed_on = on_stages.get(card["file"], set())
        if set(card["stages"]) != listed_on:
            err(f"/cards/{ci}/stages", "coverage", f"{card['file']} is on stages {sorted(listed_on)} but the card says {sorted(card['stages'])}")

    flagged = {(f["kind"], f["target"]["id"]) for f in atlas["flags"]}
    for wi, w in enumerate(atlas["workflows"]):
        base = f"/workflows/{wi}"
        edges = {(p["from"], p["to"]) for p in w["paths"]}
        trunk = {s for p in w["paths"] if not p.get("variants") for s in (p["from"], p["to"])}

        # Rule 5: variants follow real paths and leave from / rejoin the shared flow.
        for vi, v in enumerate(w["variants"]):
            route = v["route"]
            for a, b in zip(route, route[1:]):
                if (a, b) not in edges:
                    err(f"{base}/variants/{vi}/route", "variants", f"{v['id']} goes {a} -> {b} but there is no such path")
            shared = trunk | {s for o in w["variants"] if o["id"] != v["id"] for s in o["route"]}
            for end, label in ((route[0], "branches off"), (route[-1], "merges back")):
                if end not in shared:
                    err(f"{base}/variants/{vi}/route", "variants", f"{v['id']} {label} at {end}, which no other route uses")

        # Rule 6: one start, at least one end, nothing orphaned unless flagged.
        kinds = Counter(s["kind"] for s in w["stages"])
        if kinds["start"] != 1:
            err(f"{base}/stages", "shape", f"{w['id']} has {kinds['start']} start stages, needs exactly 1")
        if not kinds["end"]:
            err(f"{base}/stages", "shape", f"{w['id']} has no end stage")
        start = next((s["id"] for s in w["stages"] if s["kind"] == "start"), None)
        seen, todo = {start}, [start]
        while todo:
            here = todo.pop()
            for a, b in edges:
                if a == here and b not in seen:
                    seen.add(b)
                    todo.append(b)
        for si, s in enumerate(w["stages"]):
            if s["id"] not in seen and ("unreachable", s["id"]) not in flagged:
                err(f"{base}/stages/{si}", "shape", f"{s['id']} cannot be reached from the start; connect it or flag it unreachable")
            if s["kind"] != "end" and not any(a == s["id"] for a, _ in edges) and ("dead_end", s["id"]) not in flagged:
                err(f"{base}/stages/{si}", "shape", f"{s['id']} leads nowhere; add a path, make it an end, or flag it dead_end")

    # Rule 7: stage names and descriptions read as business language.
    banned = banned_words()
    names = {s["name"] for s in scan["symbols"]} | {s["name"].rsplit(".", 1)[-1] for s in scan["symbols"]}
    for sid, (wi, si) in stages.items():
        s = atlas["workflows"][wi]["stages"][si]
        for field in ("name", "description"):
            text = s[field]
            where = f"/workflows/{wi}/stages/{si}/{field}"
            for word in banned:
                if re.search(rf"(?<![\w-]){re.escape(word)}s?(?![\w-])", text, re.I):
                    err(where, "plain-language", f"'{word}' is jargon; say what it means for the business")
            code = CODE_LIKE.search(text) or next((m for m in re.finditer(r"\b[A-Z][a-z]+[A-Z]\w*\b", text) if m.group(0) in names), None)
            if code:
                err(where, "plain-language", f"'{code.group(0)}' looks like code; identifiers belong in files[].label")

    # Rule 8: no secret values anywhere.
    for where, value in strings(atlas):
        if redact(value)[1]:
            err(where, "secret", "contains what looks like a secret value; remove it")

    # A human-locked item whose code moved on is kept on purpose and flagged stale_override (see merge.py):
    # its broken citations are expected, everything else about it is still checked.
    items = pointers(atlas)
    stale = [items[(f["target"]["type"], f["target"]["id"])] for f in atlas["flags"]
             if f["kind"] == "stale_override" and (f["target"]["type"], f["target"]["id"]) in items]
    stale += [f"/flags/{i}" for i, f in enumerate(atlas["flags"]) if f["kind"] == "stale_override"]
    return [e for e in errors if e["rule"] not in STALE_TOLERATED
            or not any(e["where"] == p or e["where"].startswith(p + "/") for p in stale)]


STALE_TOLERATED = {"evidence", "symbol", "refs", "coverage"}


def link_id(link: dict) -> str:
    return f"{link['from_stage']}->{link['to_stage']}"


def pointers(atlas: dict) -> dict[tuple[str, str], str]:
    """(flag target type, id) -> JSON pointer, for every item a human can lock. A card is targeted as its file."""
    out = {("module", m["id"]): f"/modules/{i}" for i, m in enumerate(atlas["modules"])}
    out |= {("link", link_id(link)): f"/links/{i}" for i, link in enumerate(atlas.get("links", []))}
    out |= {("file", c["file"]): f"/cards/{i}" for i, c in enumerate(atlas["cards"])}
    out |= {("shared_system", s["id"]): f"/shared_systems/{i}" for i, s in enumerate(atlas["shared_systems"])}
    for wi, w in enumerate(atlas["workflows"]):
        out[("workflow", w["id"])] = f"/workflows/{wi}"
        for key, kind in (("stages", "stage"), ("paths", "path"), ("variants", "variant")):
            out |= {(kind, x["id"]): f"/workflows/{wi}/{key}/{i}" for i, x in enumerate(w[key])}
    return out


def check_citation(ev: dict, scan_files: dict, symbols: dict) -> list[tuple[str, str]]:
    """Rules 1 + 2 for one citation: a scanned file, real lines, and a cited symbol that really sits there."""
    f = scan_files.get(ev["path"])
    if f is None:
        return [("evidence", f"{ev['path']} is not a scanned file")]
    problems = []
    # ponytail: scan stores newline count; +1 allows a last line without a trailing newline
    if not 1 <= ev["start_line"] <= ev["end_line"] <= f["loc"] + 1:
        problems.append(("evidence", f"lines {ev['start_line']}-{ev['end_line']} are outside {ev['path']} ({f['loc']} lines)"))
    if "symbol" in ev:
        sym = symbols.get((ev["path"], ev["symbol"]))
        if sym is None:
            problems.append(("symbol", f"{ev['symbol']} is not defined in {ev['path']}"))
        elif not (ev["start_line"] <= sym["end_line"] and sym["start_line"] <= ev["end_line"]):
            problems.append(("symbol", f"{ev['symbol']} is at lines {sym['start_line']}-{sym['end_line']}, "
                                       f"not {ev['start_line']}-{ev['end_line']}"))
    return problems


def evidence(node, where=""):
    """(pointer, evidence) for every citation in the document."""
    if isinstance(node, dict):
        for i, ev in enumerate(node.get("evidence", [])):
            yield f"{where}/evidence/{i}", ev
        for k, v in node.items():
            if k != "evidence":
                yield from evidence(v, f"{where}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from evidence(v, f"{where}/{i}")


def strings(node, where=""):
    if isinstance(node, str):
        yield where or "/", node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from strings(v, f"{where}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from strings(v, f"{where}/{i}")


def report(errors: list[dict]) -> str:
    if not errors:
        return "Valid."
    return "\n".join(f"{n}. [{e['rule']}] {e['where']}: {e['message']}" for n, e in enumerate(errors, 1))
