"""The hand-written sample atlas must be valid and must tell the truth about the fixture."""
import hashlib
import json
from pathlib import Path

from scan import scan
from validate import report, validate

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "leave-desk"
ATLAS = json.loads((ROOT / "examples" / "leave-desk.atlas.json").read_text())


def test_passes_the_validator():
    errors = validate(ATLAS, scan(FIXTURE))
    assert not errors, report(errors)


def test_files_match_fixture_on_disk():
    on_disk = {p.relative_to(FIXTURE).as_posix(): p for p in FIXTURE.rglob("*")
               if p.is_file() and "__pycache__" not in p.parts and ".atlas" not in p.parts}
    assert {f["path"] for f in ATLAS["files"]} == set(on_disk)
    for f in ATLAS["files"]:
        assert f["sha256"] == hashlib.sha256(on_disk[f["path"]].read_bytes()).hexdigest(), f"{f['path']} changed; update the atlas"
