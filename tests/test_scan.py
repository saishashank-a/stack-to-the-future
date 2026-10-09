"""Milestone (b) exit check: the scanner finds what's planted in leave-desk and agrees with the golden atlas."""
import json
import shutil
from pathlib import Path

import jsonschema
import pytest

import atlas
import scan as scanner
from cluster import cluster

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "leave-desk"
GOLDEN = json.loads((ROOT / "examples" / "leave-desk.atlas.json").read_text())
SCHEMA = json.loads((ROOT / "skills" / "stack-to-the-future" / "schema" / "scan.schema.json").read_text())


@pytest.fixture(scope="module")
def scan():
    result = scanner.scan(FIXTURE)
    result["clusters"] = cluster(result)
    return result


def test_matches_schema_and_is_deterministic(scan):
    jsonschema.validate(scan, SCHEMA)
    again = scanner.scan(FIXTURE)
    again["clusters"] = cluster(again)
    assert again == scan


def test_entry_points(scan):
    found = {(e["kind"], e["label"], e["symbol"]) for e in scan["entry_points"]}
    assert found == {
        ("api_route", "POST /", "submit_leave"),  # router prefix /leave arrives with the FastAPI adapter (f)
        ("api_route", "GET /mine", "my_leave"),
        ("api_route", "POST /{request_id}/approve", "approve_leave"),
        ("api_route", "POST /{request_id}/reject", "reject_leave"),
        ("api_route", "POST /monthly/run", "run_monthly_summary"),
        ("api_route", "GET /export", "export"),
        ("background_job", "leave.notify_manager", "notify_manager"),
        ("background_job", "leave.notify_decision", "notify_decision"),
        ("background_job", "reports.monthly_summary", "monthly_summary"),
    }
    golden = {ev["symbol"] for m in GOLDEN["modules"] for e in m["entry_points"] if e["kind"] != "scheduled_job"
              for ev in e["evidence"] if "symbol" in ev}
    assert golden <= {e["symbol"] for e in scan["entry_points"]}


def test_status_machine(scan):
    (machine,) = scan["status_machines"]  # Role is an enum but not a status machine
    assert (machine["enum"], machine["initial"]) == ("LeaveStatus", ["PENDING"])
    assert {(tuple(t["from"]), t["to"], t["function"]) for t in machine["transitions"]} == {
        (("PENDING",), "APPROVED", "_approve"),
        (("PENDING",), "REJECTED", "reject_by_manager"),
    }


def test_permission_branches(scan):
    assert {(b["file"], b["function"]) for b in scan["permission_branches"]} == {
        ("app/leave/service.py", "choose_route"),
        ("app/leave/service.py", "_check_reviewer"),
        ("app/shared/auth.py", "require_manager"),
        ("app/shared/auth.py", "require_hr"),
    }


def test_models(scan):
    assert {(m["name"], m["kind"]) for m in scan["models"]} == {
        ("Employee", "orm"), ("LeaveRequest", "orm"), ("AuditEntry", "orm"),
        ("LeaveRequestIn", "schema"), ("LeaveRequestOut", "schema"),
    }


def test_incomplete_code_matches_golden_flags(scan):
    found = {(i["kind"], i["file"], i["symbol"]) for i in scan["incomplete"]}
    assert found == {
        ("todo", "app/leave/balance.py", "deduct"),
        ("not_implemented", "app/reports/service.py", "export_csv"),
        ("missing_transition", "app/leave/models.py", "LeaveStatus.CANCELLED"),
    }  # and `class Base(DeclarativeBase): pass` is not a stub
    for flag in GOLDEN["flags"]:
        ev = flag["evidence"][0]
        assert any(i["file"] == ev["path"] and ev["start_line"] <= i["line"] <= ev["end_line"] for i in scan["incomplete"]), flag["id"]


def test_golden_citations_resolve_against_scan_symbols(scan):
    table = {(s["file"], s["name"]): s for s in scan["symbols"]}

    def walk(node):
        if isinstance(node, dict):
            yield from node.get("evidence", [])
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)

    for ev in walk(GOLDEN):
        if "symbol" in ev:
            sym = table[(ev["path"], ev["symbol"])]
            assert ev["start_line"] <= sym["end_line"] and sym["start_line"] <= ev["end_line"], ev


def test_clusters_agree_with_golden(scan):
    c = scan["clusters"]
    assert {m["id"]: m["role"] for m in c["modules"]} == {"core": "foundation", "leave": "business",
                                                          "reports": "business", "shared": "shared"}
    assert c["foundation"] == {g["group"]: sorted(g["files"]) for g in GOLDEN["foundation"]}
    assert set(c["shared_candidates"]) == {f for s in GOLDEN["shared_systems"] for f in s["files"]}
    (time_off,) = [w for w in c["workflows"] if "LeaveStatus" in w["status_machines"]]
    assert {"app/leave/routes.py::submit_leave", "app/leave/routes.py::approve_leave",
            "app/leave/routes.py::reject_leave"} <= set(time_off["entry_points"])
    assert c["draft_order"] == ["leave", "reports"] and not c["unassigned"]


def test_no_secret_values_anywhere(scan):
    text = json.dumps(scan)
    for secret in ("FAKE-smtp-pass-9f8a7b6c5d4e3f2a1b0c", "FAKE-db-pass-4c3b2a19"):
        assert secret not in text


def test_cli_writes_atlas_folder(tmp_path):
    repo = tmp_path / "leave-desk"
    shutil.copytree(FIXTURE, repo, ignore=shutil.ignore_patterns(".atlas"))
    atlas.main(["scan", str(repo), "--draft-limit", "1"])
    out = json.loads((repo / ".atlas" / "scan.json").read_text())
    assert out["clusters"]["draft_now"] == ["leave"]
    assert "scan.json" in (repo / ".atlas" / ".gitignore").read_text()
