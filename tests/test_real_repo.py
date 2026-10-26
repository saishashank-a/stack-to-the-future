"""PLAN section 8 smoke test: the scanner holds up on a real, permissively licensed repo, cloned at test time.

Needs the network, so it only runs when asked: STF_SMOKE=1 uv run pytest tests/test_real_repo.py
"""
import json
import os
import subprocess
from pathlib import Path

import jsonschema
import pytest

import scan as scanner
from cluster import cluster

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "plugin" / "skills" / "stack-to-the-future" / "schema" / "scan.schema.json").read_text(encoding="utf-8"))
REPO = "https://github.com/fastapi/full-stack-fastapi-template.git"  # MIT

pytestmark = pytest.mark.skipif(not os.environ.get("STF_SMOKE"), reason="network smoke test; set STF_SMOKE=1")


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    repo = tmp_path_factory.mktemp("real") / "fst"
    subprocess.run(["git", "clone", "-q", "--depth", "1", REPO, str(repo)], check=True)
    out = scanner.scan(repo)
    out["clusters"] = cluster(out)
    return out


def test_scan_is_valid_and_finds_the_api(result):
    jsonschema.validate({k: v for k, v in result.items() if k != "clusters"}, SCHEMA)
    routes = [e for e in result["entry_points"] if e["kind"] == "api_route"]
    assert len(routes) >= 15
    assert all("{API_V1_STR}/" in e["label"] for e in routes)  # router prefixes resolved through include_router
    assert any(b["test"].startswith("Depends(") for b in result["permission_branches"])  # FastAPI guards found


def test_layers_on_real_code(result):
    hints = {f["path"]: (f["hint"], f.get("group")) for f in result["files"]}
    assert not [p for p, h in hints.items() if ".gen." in p and h[0] != "ignored"]
    migrations = [p for p in hints if "/alembic/versions/" in p and p.endswith(".py")]
    assert migrations and all(hints[p] == ("foundation", "database_setup") for p in migrations)
    assert [m for m in result["clusters"]["modules"] if m["id"] == "backend" and m["workflows"]]


def test_no_secret_values(result):
    text = json.dumps(result)
    assert "changethis" not in text  # the template's placeholder secrets in .env
