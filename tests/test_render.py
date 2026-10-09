"""Milestone (e): HTML, Excalidraw and .lal renderers draw the sample atlas faithfully, offline, and never leak secrets.

Golden files live in examples/out/. Regenerate after an intended change with: UPDATE_GOLDEN=1 uv run pytest tests/test_render.py
"""
import copy
import json
import os
import re
from pathlib import Path

import jsonschema
import pytest

import atlas as cli
from render import excalidraw, html, lal, layout

ROOT = Path(__file__).resolve().parents[1]
ATLAS = json.loads((ROOT / "examples" / "leave-desk.atlas.json").read_text(encoding="utf-8"))
GOLDEN = ROOT / "examples" / "out"
LAL_SCHEMA = json.loads((ROOT / "skills" / "stack-to-the-future" / "schema" / "lal.schema.json").read_text(encoding="utf-8"))
RENDERERS = {"html": html.render, "excalidraw": excalidraw.render, "lal": lal.render}
CANCEL = "request-time-off/employee-cancels"


@pytest.fixture(scope="module")
def out():
    return {fmt: render(ATLAS) for fmt, render in RENDERERS.items()}


@pytest.mark.parametrize("fmt", RENDERERS)
def test_golden(out, fmt):
    path = GOLDEN / f"leave-desk.atlas.{fmt}"
    if os.environ.get("UPDATE_GOLDEN"):
        path.parent.mkdir(exist_ok=True)
        path.write_text(out[fmt], encoding="utf-8", newline="\n")
    assert out[fmt] == path.read_text(encoding="utf-8"), f"{path.name} changed; rerun with UPDATE_GOLDEN=1 if intended"
    assert out[fmt] == RENDERERS[fmt](ATLAS)  # deterministic


def test_html_is_self_contained(out):
    page = out["html"]
    assert not re.search(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""", page, re.I)
    assert not re.search(r"""@import|url\(\s*["']?\s*(?:https?:)?//""", page, re.I)
    assert "<script src" not in page and 'rel="stylesheet"' not in page
    for wf in ATLAS["workflows"]:
        for stage in wf["stages"]:
            assert f'data-stage="{stage["id"]}"' in page
    for card in ATLAS["cards"]:
        assert f'data-card="{card["file"]}"' in page


def test_excalidraw_is_valid_and_bound(out):
    doc = json.loads(out["excalidraw"])
    assert (doc["type"], doc["version"]) == ("excalidraw", 2)
    els = {e["id"]: e for e in doc["elements"]}
    assert len(els) == len(doc["elements"]), "duplicate element ids"
    frames = {e["id"] for e in doc["elements"] if e["type"] == "frame"}
    assert len(frames) == 1 + len(ATLAS["workflows"])
    for e in doc["elements"]:
        assert e["frameId"] is None or e["frameId"] in frames
        if e["type"] == "text" and e["containerId"]:
            assert {"type": "text", "id": e["id"]} in els[e["containerId"]]["boundElements"]
        if e["type"] == "arrow":
            for end in ("startBinding", "endBinding"):
                target = els[e[end]["elementId"]]
                assert {"type": "arrow", "id": e["id"]} in target["boundElements"]


def test_lal_matches_schema_and_references_resolve(out):
    doc = json.loads(out["lal"])
    jsonschema.validate(doc, LAL_SCHEMA)
    frames, layers = {f["id"] for f in doc["frames"]}, {l["id"] for l in doc["layers"]}
    nodes = {n["id"] for n in doc["nodes"]}
    ids = [x["id"] for key in ("frames", "nodes", "connectors", "callouts") for x in doc[key]]
    assert len(ids) == len(set(ids)), "ids must be unique across the file"
    for item in doc["nodes"] + doc["connectors"] + doc["callouts"]:
        assert item["frame"] in frames and item["layer"] in layers
    for n in doc["nodes"]:
        assert n["link"] is None or n["link"] in frames
    for c in doc["connectors"]:
        assert {c["from"], c["to"]} <= nodes
    for c in doc["callouts"]:
        assert c["target"] is None or c["target"] in nodes


def test_incomplete_is_dashed_everywhere(out):
    assert re.search(rf'<g class="node k-end incomplete" data-stage="{CANCEL}"', out["html"])
    assert ".incomplete .shape,.incomplete path{stroke-dasharray" in out["html"]
    ex = {e["id"]: e for e in json.loads(out["excalidraw"])["elements"]}
    assert ex[f"stage:{CANCEL}"]["strokeStyle"] == "dashed"
    assert ex["path:request-time-off/p-booked-cancel"]["strokeStyle"] == "dashed"
    doc = json.loads(out["lal"])
    assert next(n for n in doc["nodes"] if n["id"] == f"stage:{CANCEL}")["style"]["stroke"] == "dashed"
    assert next(c for c in doc["connectors"] if c["id"] == "path:request-time-off/p-booked-cancel")["style"]["stroke"] == "dashed"


def test_variants_branch_off_the_trunk_and_merge():
    p = layout.plate(ATLAS["workflows"][0], ATLAS)
    cy = {n["id"].split("/")[1]: n["cy"] for n in p["nodes"]}
    trunk = {"submit", "choose-route", "deduct-balance", "notify-employee", "leave-booked"}
    assert len({cy[s] for s in trunk}) == 1
    branches = {cy["approve-directly"], cy["self-approve"], cy["notify-manager"]}
    assert len(branches) == 3 and cy["submit"] not in branches
    merging = {e["from"].split("/")[1] for e in p["edges"] if e.get("merge")}
    assert merging == {"approve-directly", "self-approve", "manager-review"}


@pytest.mark.parametrize("fmt", RENDERERS)
def test_planted_secret_refuses_to_render(fmt):
    key = "sk_" + "live_" + "Q" * 24
    leaky = copy.deepcopy(ATLAS)
    leaky["workflows"][0]["stages"][0]["files"][0]["label"] = f"routes.py: {key}"  # bone labels appear in every format
    with pytest.raises(ValueError, match="refusing to render"):
        RENDERERS[fmt](leaky)
    clipped = copy.deepcopy(ATLAS)  # long enough that the drawn label is truncated mid-secret
    clipped["workflows"][0]["stages"][0]["files"][0]["label"] = "service.py: connect with " + "ghp_" + "b2" * 20
    with pytest.raises(ValueError, match="refusing to render"):
        RENDERERS[fmt](clipped)
    if fmt == "html":  # cards are HTML-only
        carded = copy.deepcopy(ATLAS)
        carded["cards"][0]["role"] = f"Pays with {key}"
        with pytest.raises(ValueError, match="refusing to render"):
            html.render(carded)


def test_cli_render(tmp_path):
    (tmp_path / ".atlas").mkdir()
    (tmp_path / ".atlas" / "atlas.json").write_text(json.dumps(ATLAS), encoding="utf-8")
    cli.main(["render", "--root", str(tmp_path)])
    assert {p.name for p in (tmp_path / ".atlas" / "out").iterdir()} == {"atlas.html", "atlas.excalidraw", "atlas.lal"}

    leaky = copy.deepcopy(ATLAS)
    leaky["project"]["summary"] = "token = 'ghp_" + "a1" * 18 + "'"
    other = tmp_path / "leaky"
    (other / ".atlas").mkdir(parents=True)
    (other / ".atlas" / "atlas.json").write_text(json.dumps(leaky), encoding="utf-8")
    with pytest.raises(ValueError):
        cli.main(["render", "--root", str(other), "--format", "excalidraw,html"])
    assert not (other / ".atlas" / "out" / "atlas.excalidraw").exists()


def test_trunk_has_no_more_lanes_above_than_below():
    """Phones show the top of a plate first, so the trunk (start stage) should sit as high as the lanes allow."""
    for w in ATLAS["workflows"]:
        nodes = layout.plate(w, ATLAS)["nodes"]
        trunk = next(n["cy"] for n in nodes if n["kind"] == "start")
        rows = {n["cy"] for n in nodes}
        assert len({r for r in rows if r < trunk}) <= len({r for r in rows if r > trunk}), w["id"]
