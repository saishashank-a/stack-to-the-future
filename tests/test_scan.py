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
GOLDEN = json.loads((ROOT / "examples" / "leave-desk.atlas.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "skills" / "stack-to-the-future" / "schema" / "scan.schema.json").read_text(encoding="utf-8"))


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
        ("api_route", "POST /leave", "submit_leave"),  # router prefixes resolved by the FastAPI adapter
        ("api_route", "GET /leave/mine", "my_leave"),
        ("api_route", "POST /leave/{request_id}/approve", "approve_leave"),
        ("api_route", "POST /leave/{request_id}/reject", "reject_leave"),
        ("api_route", "POST /reports/monthly/run", "run_monthly_summary"),
        ("api_route", "GET /reports/export", "export"),
        ("background_job", "leave.notify_manager", "notify_manager"),
        ("background_job", "leave.notify_decision", "notify_decision"),
        ("background_job", "reports.monthly_summary", "monthly_summary"),
        ("scheduled_job", 'reports.monthly_summary (crontab(day_of_month="1", hour="6", minute="0"))', "<module>"),
    }
    # Every golden entry point, of every kind, is found: same label for routes and jobs, overlapping lines for schedules.
    for golden in (e for m in GOLDEN["modules"] for e in m["entry_points"]):
        if golden["kind"] == "scheduled_job":
            ev = golden["evidence"][0]
            assert any(e["kind"] == "scheduled_job" and e["file"] == ev["path"] and e["start_line"] <= ev["end_line"]
                       and ev["start_line"] <= e["end_line"] and e["label"].startswith("reports.monthly_summary")
                       for e in scan["entry_points"]), golden
        else:
            assert (golden["kind"], golden["label"]) in {(e["kind"], e["label"]) for e in scan["entry_points"]}, golden


def test_status_machine(scan):
    (machine,) = scan["status_machines"]  # Role is an enum but not a status machine
    assert (machine["enum"], machine["initial"]) == ("LeaveStatus", ["PENDING"])
    assert {(tuple(t["from"]), t["to"], t["function"]) for t in machine["transitions"]} == {
        (("PENDING",), "APPROVED", "_approve"),
        (("PENDING",), "REJECTED", "reject_by_manager"),
    }
    assert machine["columns"] == [{"file": "app/leave/models.py", "model": "LeaveRequest", "field": "status", "line": 46}]


def test_permission_branches(scan):
    assert {(b["file"], b["function"]) for b in scan["permission_branches"] if not b["test"].startswith("Depends(")} == {
        ("app/leave/service.py", "choose_route"),
        ("app/leave/service.py", "_check_reviewer"),
        ("app/shared/auth.py", "require_manager"),
        ("app/shared/auth.py", "require_hr"),
    }
    # Routes guarded through Depends (FastAPI adapter), including the reports router's router-level dependency.
    assert {(b["function"], b["test"]) for b in scan["permission_branches"] if b["test"].startswith("Depends(")} == {
        ("submit_leave", "Depends(current_employee)"), ("my_leave", "Depends(current_employee)"),
        ("approve_leave", "Depends(require_manager)"), ("reject_leave", "Depends(require_manager)"),
        ("run_monthly_summary", "Depends(require_hr)"), ("export", "Depends(require_hr)"),
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
    # Celery send_task("reports.monthly_summary") links the manual trigger to the monthly job: one skeleton.
    (summary,) = [w for w in c["workflows"] if "app/reports/tasks.py::monthly_summary" in w["entry_points"]]
    assert "app/reports/routes.py::run_monthly_summary" in summary["entry_points"]
    assert c["draft_order"] == ["leave", "reports"] and not c["unassigned"]


def test_no_secret_values_anywhere(scan):
    text = json.dumps(scan)
    for secret in ("FAKE-smtp-pass-9f8a7b6c5d4e3f2a1b0c", "FAKE-db-pass-4c3b2a19"):
        assert secret not in text


def test_cli_writes_atlas_folder(tmp_path):
    repo = tmp_path / "leave-desk"
    shutil.copytree(FIXTURE, repo, ignore=shutil.ignore_patterns(".atlas"))
    atlas.main(["scan", str(repo), "--draft-limit", "1"])
    out = json.loads((repo / ".atlas" / "scan.json").read_text(encoding="utf-8"))
    assert out["clusters"]["draft_now"] == ["leave"]
    assert "scan.json" in (repo / ".atlas" / ".gitignore").read_text(encoding="utf-8")


def test_generated_tests_configs_and_migrations_are_not_business(tmp_path):
    files = {
        "web/src/client/sdk.gen.ts": "export const x = 1;\n",
        "web/src/routeTree.gen.ts": "export const r = 1;\n",
        "web/src/types.d.ts": "declare const y: number;\n",
        "web/src/__generated__/graphql.ts": "export const g = 1;\n",
        "web/src/cart.test.tsx": "test('x', () => {});\n",
        "web/vite.config.ts": "export default {};\n",
        "web/src/cart.tsx": "export function Cart() { return null; }\n",
        "api/proto/user_pb2.py": "X = 1\n",
        "api/alembic/env.py": "def run_migrations_online():\n    pass\n",
        "api/alembic/versions/0001_init.py": "def upgrade():\n    pass\n",
        "api/shop/migrations/0002_price.py": "def forwards():\n    pass\n",
        "api/shop/orders.py": "def place():\n    return 1\n",
    }
    for path, body in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(body, encoding="utf-8")
    hints = {f["path"]: (f["hint"], f.get("group")) for f in scanner.scan(tmp_path)["files"]}
    for p in ["web/src/client/sdk.gen.ts", "web/src/routeTree.gen.ts", "web/src/types.d.ts",
              "web/src/__generated__/graphql.ts", "web/src/cart.test.tsx", "api/proto/user_pb2.py"]:
        assert hints[p] == ("ignored", None), p
    assert hints["web/vite.config.ts"] == ("foundation", "configuration")
    for p in ["api/alembic/env.py", "api/alembic/versions/0001_init.py", "api/shop/migrations/0002_price.py"]:
        assert hints[p] == ("foundation", "database_setup"), p
    assert hints["web/src/cart.tsx"] == hints["api/shop/orders.py"] == ("business", None)


def test_sqlmodel_table_symbols_match_the_schema(tmp_path):
    (tmp_path / "models.py").write_text(
        "from sqlmodel import Field, SQLModel\n\n"
        "class Item(SQLModel, table=True):\n    id: int = Field(primary_key=True)\n", encoding="utf-8")
    result = scanner.scan(tmp_path)
    jsonschema.validate(result, SCHEMA)
    assert next(s for s in result["symbols"] if s["name"] == "Item")["table"] is True
