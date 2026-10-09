"""Milestone (g): walkthrough context is complete and safe; check-walkthrough accepts honest walkthroughs only."""
import json
import shutil
from pathlib import Path

import pytest

import atlas
from walkthrough import check, context

ROOT = Path(__file__).resolve().parents[1]
WALKTHROUGH = (ROOT / "tests" / "data" / "walkthrough-leave-service.md").read_text()
FAKE_SECRET = "FAKE-smtp-pass-9f8a7b6c5d4e3f2a1b0c"


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    repo = tmp_path_factory.mktemp("w") / "leave-desk"
    shutil.copytree(ROOT / "fixtures" / "leave-desk", repo, ignore=shutil.ignore_patterns(".atlas"))
    atlas.main(["scan", str(repo)])
    shutil.copy(ROOT / "examples" / "leave-desk.atlas.json", repo / ".atlas" / "atlas.json")
    return repo


@pytest.fixture(scope="module")
def scan(repo):
    return json.loads((repo / ".atlas" / "scan.json").read_text())


def test_context_has_card_stages_links_facts_and_source(repo):
    text = context(repo, "app/leave/service.py")
    for expected in ["The rulebook", "request-time-off/choose-route", "choose_route (function) 13-19",
                     "app/leave/routes.py::submit_leave line 16 -> submit_request",
                     "_approve line 75 -> app/leave/balance.py::deduct",
                     "PENDING -> APPROVED in _approve line 73", "permission check in _check_reviewer line 68",
                     '13 | def choose_route(employee: Employee, days: float) -> str:']:
        assert expected in text, expected


def test_context_is_redacted_and_refuses_secrets(repo):
    assert FAKE_SECRET not in context(repo, "app/core/config.py")
    for path in [".env.example", "../outside.py"]:
        with pytest.raises(ValueError):
            context(repo, path)
    with pytest.raises(SystemExit):
        atlas.main(["walkthrough-context", ".env.example", "--root", str(repo)])


def test_real_walkthrough_passes(scan):
    assert check(WALKTHROUGH, scan) == []


@pytest.mark.parametrize("change, rule", [
    (lambda w: w.replace("service.py:13-19 choose_route", "service.py:13-190 choose_route"), "evidence"),
    (lambda w: w.replace("service.py:13-19 choose_route", "service.py:13-19 pick_route"), "symbol"),
    (lambda w: w.replace("service.py:65-69 _check_reviewer", "service.py:13-19 _check_reviewer"), "symbol"),
    (lambda w: w.replace("`app/leave/service.py:13-19 choose_route`", ""), "steps"),
    (lambda w: w + f'\nThe mail login is `smtp_password: str = "{FAKE_SECRET}"`.\n', "secret"),
    (lambda w: w.replace("Every request gets", "The choose_route function gives every request"), "plain-language"),
    (lambda w: w.split("## Step by step")[0], "steps"),
])
def test_dishonest_walkthroughs_are_rejected(scan, change, rule):
    errors = check(change(WALKTHROUGH), scan)
    assert rule in {e["rule"] for e in errors}, errors


def test_cli_exit_codes(repo, tmp_path):
    atlas.main(["check-walkthrough", str(ROOT / "tests" / "data" / "walkthrough-leave-service.md"), "--root", str(repo)])
    bad = tmp_path / "bad.md"
    bad.write_text(WALKTHROUGH.replace("13-19 choose_route", "13-19 pick_route"))
    with pytest.raises(SystemExit) as e:
        atlas.main(["check-walkthrough", str(bad), "--root", str(repo)])
    assert e.value.code == 1
