"""Milestone (c): the validator accepts honest atlases and rejects each kind of wrong claim with the right rule."""
import copy
import json
from pathlib import Path

import pytest

from scan import scan
from validate import banned_words, report, validate

ROOT = Path(__file__).resolve().parents[1]
SCAN = scan(ROOT / "fixtures" / "leave-desk")
GOLDEN = json.loads((ROOT / "examples" / "leave-desk.atlas.json").read_text())
DRAFT = json.loads((ROOT / "tests" / "data" / "leave-desk.claude-draft.json").read_text())


def test_claude_draft_is_valid():
    errors = validate(DRAFT, SCAN)
    assert not errors, report(errors)


def test_banned_words_come_from_the_reference():
    assert {"endpoint", "ORM", "handler", "API"} <= set(banned_words())


def stage(atlas, sid):
    return next(s for w in atlas["workflows"] for s in w["stages"] if s["id"] == sid)


def fabricated_symbol(a):
    stage(a, "request-time-off/choose-route")["evidence"][0]["symbol"] = "pick_route"


def out_of_range(a):
    stage(a, "request-time-off/choose-route")["evidence"][0].update(start_line=70, end_line=900)


def symbol_outside_range(a):
    stage(a, "request-time-off/choose-route")["evidence"][0].update(start_line=40, end_line=41)


def dangling_slug(a):
    a["workflows"][0]["paths"][0]["to"] = "request-time-off/nowhere"


def unmerged_variant(a):
    a["workflows"][0]["variants"][1]["route"][-1] = "request-time-off/self-approve"
    a["workflows"][0]["variants"][1]["route"] = ["request-time-off/choose-route", "request-time-off/self-approve"]
    for p in a["workflows"][0]["paths"]:
        if p["from"] == "request-time-off/self-approve":
            p["from"] = "request-time-off/notify-employee"


def missing_card(a):
    a["cards"] = [c for c in a["cards"] if c["file"] != "app/leave/balance.py"]


def foundation_twice(a):
    a["foundation"][0]["files"].append("app/core/database.py")


def jargon_name(a):
    stage(a, "request-time-off/submit")["name"] = "Employee calls the API endpoint"


def code_in_name(a):
    stage(a, "request-time-off/choose-route")["name"] = "choose_route picks an approver"


def leaked_secret(a):
    a["cards"][0]["if_removed"] = 'smtp_password = "FAKE-smtp-pass-9f8a7b6c5d4e3f2a1b0c"'


def unflagged_orphan(a):
    a["workflows"][0]["paths"] = [p for p in a["workflows"][0]["paths"] if p["to"] != "request-time-off/employee-cancels"]


@pytest.mark.parametrize("break_it, rule, where", [
    (fabricated_symbol, "symbol", "/workflows/0/stages/1/evidence/0"),
    (out_of_range, "evidence", "/workflows/0/stages/1/evidence/0"),
    (symbol_outside_range, "symbol", "/workflows/0/stages/1/evidence/0"),
    (dangling_slug, "refs", "/workflows/0/paths/0/to"),
    (unmerged_variant, "variants", "/workflows/0/variants/1/route"),
    (missing_card, "coverage", "/files/7"),
    (foundation_twice, "coverage", "/files/5"),
    (jargon_name, "plain-language", "/workflows/0/stages/0/name"),
    (code_in_name, "plain-language", "/workflows/0/stages/1/name"),
    (leaked_secret, "secret", "/cards/0/if_removed"),
    (unflagged_orphan, "shape", "/workflows/0/stages/10"),
])
def test_rejects(break_it, rule, where):
    atlas = copy.deepcopy(GOLDEN)
    break_it(atlas)
    errors = validate(atlas, SCAN)
    assert any(e["rule"] == rule and e["where"] == where for e in errors), report(errors)


def test_schema_errors_stop_early_with_a_pointer():
    atlas = copy.deepcopy(GOLDEN)
    del atlas["workflows"][0]["stages"][0]["evidence"]
    errors = validate(atlas, SCAN)
    assert [e["rule"] for e in errors] == ["schema"] and errors[0]["where"] == "/workflows/0/stages/0"
