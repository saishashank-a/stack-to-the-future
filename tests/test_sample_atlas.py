"""The hand-written sample atlas must be valid and must tell the truth about the fixture.

ponytail: stdlib `ast` stands in for the tree-sitter symbol table until milestone (c)'s validator exists.
"""
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "leave-desk"
ATLAS = json.loads((ROOT / "examples" / "leave-desk.atlas.json").read_text())
SCHEMA = json.loads((ROOT / "skills" / "stack-to-the-future" / "schema" / "atlas.schema.json").read_text())
FAKE_SECRETS = ["FAKE-smtp-pass-9f8a7b6c5d4e3f2a1b0c", "FAKE-db-pass-4c3b2a19"]


def symbols(path: Path) -> dict[str, tuple[int, int]]:
    """Qualified name -> (first line incl. decorators, last line) for defs, classes and assignments."""
    found = {}

    def walk(body, prefix):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                found[prefix + node.name] = (start, node.end_lineno)
                if isinstance(node, ast.ClassDef):
                    walk(node.body, f"{prefix}{node.name}.")
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        found[prefix + t.id] = (node.lineno, node.end_lineno)

    walk(ast.parse(path.read_text()).body, "")
    return found


def evidence(node):
    """Every evidence object anywhere in the atlas."""
    if isinstance(node, dict):
        for item in node.get("evidence", []):
            yield item
        for value in node.values():
            yield from evidence(value)
    elif isinstance(node, list):
        for value in node:
            yield from evidence(value)


def test_matches_schema():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    jsonschema.validate(ATLAS, SCHEMA, format_checker=jsonschema.FormatChecker())


def test_files_match_fixture_on_disk():
    on_disk = {p.relative_to(FIXTURE).as_posix(): p for p in FIXTURE.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    assert {f["path"] for f in ATLAS["files"]} == set(on_disk)
    for f in ATLAS["files"]:
        assert f["sha256"] == hashlib.sha256(on_disk[f["path"]].read_bytes()).hexdigest(), f"{f['path']} changed; update the atlas"


def test_every_citation_points_at_real_code():
    for ev in evidence(ATLAS):
        path = FIXTURE / ev["path"]
        assert path.is_file(), ev
        assert 1 <= ev["start_line"] <= ev["end_line"] <= len(path.read_text().splitlines()), ev
        if "symbol" in ev:
            table = symbols(path)
            assert ev["symbol"] in table, f"unknown symbol {ev}"
            start, end = table[ev["symbol"]]
            assert ev["start_line"] <= end and start <= ev["end_line"], f"citation misses its symbol {ev}"


def test_references_resolve():
    modules = {m["id"] for m in ATLAS["modules"]}
    workflows = {w["id"]: w for w in ATLAS["workflows"]}
    stages = {s["id"] for w in workflows.values() for s in w["stages"]}
    files = {f["path"] for f in ATLAS["files"]}

    for m in ATLAS["modules"]:
        assert set(m["workflows"]) <= set(workflows) and set(m["files"]) <= files
    for w in workflows.values():
        assert w["module"] in modules
        variants = {v["id"] for v in w["variants"]}
        own = {s["id"] for s in w["stages"]}
        for p in w["paths"]:
            assert {p["from"], p["to"]} <= own and set(p.get("variants", [])) <= variants, p
        for s in w["stages"]:
            assert {f["file"] for f in s["files"]} <= files, s["id"]
    for link in ATLAS["links"]:
        assert {link["from_stage"], link["to_stage"]} <= stages
    for card in ATLAS["cards"]:
        assert card["file"] in files and set(card["stages"]) <= stages, card["file"]
    for system in ATLAS["shared_systems"]:
        assert set(system["files"]) <= files and set(system["used_by_stages"]) <= stages
    for flag in ATLAS["flags"]:
        assert flag["target"]["id"] in {"stage": stages, "file": files, "workflow": set(workflows)}[flag["target"]["type"]] or flag["target"]["type"] == "path"


def test_layers_are_covered_exactly_once():
    cards = Counter(c["file"] for c in ATLAS["cards"])
    grouped = Counter(f for g in ATLAS["foundation"] for f in g["files"])
    for f in ATLAS["files"]:
        assert cards[f["path"]] == (f["layer"] == "business"), f"card count wrong for {f['path']}"
        assert grouped[f["path"]] == (f["layer"] == "foundation"), f"foundation grouping wrong for {f['path']}"


def test_variants_branch_and_merge_on_one_diagram():
    for w in ATLAS["workflows"]:
        edges = {(p["from"], p["to"]) for p in w["paths"]}
        for v in w["variants"]:
            route = v["route"]
            assert all(step in edges for step in zip(route, route[1:])), f"{v['id']} route skips a path"
            others = {s for o in w["variants"] if o["id"] != v["id"] for s in o["route"]}
            assert route[0] in others and route[-1] in others, f"{v['id']} does not merge back"


def test_no_secret_values_leak():
    text = json.dumps(ATLAS)
    for secret in FAKE_SECRETS:
        assert secret not in text
