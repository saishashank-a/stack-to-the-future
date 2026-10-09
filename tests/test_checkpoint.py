"""Milestone (d) exit check: cache, stale detection after an edit, locked corrections surviving, deleted evidence."""
import copy
import json
import shutil
from pathlib import Path

import pytest

import atlas
import checkpoint
import scan as scanner
import validate

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "examples" / "leave-desk.atlas.json"
GOLDEN = json.loads(GOLDEN_PATH.read_text())


@pytest.fixture
def repo(tmp_path):
    """A scanned copy of leave-desk with the golden atlas approved as its atlas.json."""
    repo = tmp_path / "leave-desk"
    shutil.copytree(ROOT / "fixtures" / "leave-desk", repo, ignore=shutil.ignore_patterns(".atlas"))
    atlas.main(["scan", str(repo)])
    atlas.main(["merge", str(GOLDEN_PATH), "--root", str(repo), "--approve"])
    return repo


def read(repo, name):
    return json.loads((repo / ".atlas" / name).read_text())


def write(repo, name, doc):
    path = repo / ".atlas" / name
    path.write_text(json.dumps(doc))
    return str(path)


def test_cache_reused_for_every_python_file(repo, monkeypatch):
    first = read(repo, "scan.json")
    monkeypatch.setattr(scanner, "analyze_python", lambda data: pytest.fail("cache miss on an unchanged file"))
    atlas.main(["scan", str(repo)])
    assert read(repo, "scan.json") == first
    monkeypatch.setattr(scanner, "SCAN_VERSION", "next")  # a scanner upgrade must recompute, not reuse
    with pytest.raises(pytest.fail.Exception):
        scanner.scan(repo, repo / ".atlas" / "cache")


def test_edit_marks_only_what_cites_the_file(repo, capsys):
    balance = repo / "app" / "leave" / "balance.py"
    balance.write_text(balance.read_text() + "\n# reviewed\n")
    atlas.main(["scan", str(repo)])
    redraft, review = checkpoint.stale(read(repo, "atlas.json"), read(repo, "scan.json"))
    assert [i.split(":")[0] for i in redraft] == [
        "card app/leave/balance.py", "stage request-time-off/submit", "stage request-time-off/deduct-balance", "flag carry-over-todo"]
    assert review == []

    locked = read(repo, "atlas.json")
    next(c for c in locked["cards"] if c["file"] == "app/leave/balance.py")["locked"] = True
    redraft, review = checkpoint.stale(locked, read(repo, "scan.json"))
    assert review == ["card app/leave/balance.py: file changed"] and len(redraft) == 3


def test_human_correction_survives_a_fresh_draft(repo, capsys):
    corrected = read(repo, "atlas.json")
    stage = corrected["workflows"][0]["stages"][1]
    assert stage["id"] == "request-time-off/choose-route"
    stage.update(name="Work out who signs off", provenance="human", locked=True)
    write(repo, "atlas.json", corrected)

    atlas.main(["merge", str(GOLDEN_PATH), "--root", str(repo)])  # fresh draft still says "Decide who needs to approve"
    assert "Work out who signs off  [request-time-off/choose-route]" in capsys.readouterr().out
    atlas.main(["merge", str(GOLDEN_PATH), "--root", str(repo), "--approve"])
    assert read(repo, "atlas.json")["workflows"][0]["stages"][1]["name"] == "Work out who signs off"


def test_deleted_evidence_raises_stale_override_and_still_validates(repo):
    corrected = read(repo, "atlas.json")
    stage = next(s for s in corrected["workflows"][0]["stages"] if s["id"] == "request-time-off/deduct-balance")
    stage.update(name="Leave comes off the balance", provenance="human", locked=True)
    write(repo, "atlas.json", corrected)

    (repo / "app" / "leave" / "balance.py").unlink()
    atlas.main(["scan", str(repo)])
    current = read(repo, "scan.json")
    draft = without(GOLDEN, "app/leave/balance.py")  # what Claude would re-draft now the file is gone
    assert validate.validate(draft, current) == []

    atlas.main(["merge", write(repo, "fresh.json", draft), "--root", str(repo), "--approve"])
    approved = read(repo, "atlas.json")
    (flag,) = [f for f in approved["flags"] if f["kind"] == "stale_override"]
    assert flag["target"] == {"type": "stage", "id": "request-time-off/deduct-balance"}
    assert validate.validate(approved, current) == []
    assert "Leave comes off the balance" in checkpoint.outline(approved)


def test_outline_names_every_item_and_where_branches_merge():
    text = checkpoint.outline(GOLDEN)
    for w in GOLDEN["workflows"]:
        for s in w["stages"]:
            assert f"[{s['id']}]" in text
    assert "Rejoins at Days come off the balance." in text
    assert "-> (1 day or less) Approved automatically" in text and "dotted: not built" in text
    assert text.index("Manager approves or declines  [") < text.index("Days come off the balance  [")  # merge point after all branches


def without(atlas_doc: dict, path: str) -> dict:
    """The atlas with every mention of a deleted file removed."""
    doc = copy.deepcopy(atlas_doc)
    doc["files"] = [f for f in doc["files"] if f["path"] != path]
    doc["cards"] = [c for c in doc["cards"] if c["file"] != path]
    doc["flags"] = [f for f in doc["flags"] if f["target"]["id"] != path]
    for m in doc["modules"]:
        m["files"] = [f for f in m["files"] if f != path]
    for w in doc["workflows"]:
        for s in w["stages"]:
            s["files"] = [f for f in s["files"] if f["file"] != path]
    for _, item in walk(doc):
        if "evidence" in item:
            item["evidence"] = [ev for ev in item["evidence"] if ev["path"] != path]
    return doc


def walk(node, where=""):
    if isinstance(node, dict):
        yield where, node
        for k, v in node.items():
            yield from walk(v, f"{where}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{where}/{i}")
