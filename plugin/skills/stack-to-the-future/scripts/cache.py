"""Per-file scan cache: <root>/.atlas/cache/<sha256>.json holds that file's analyze_python facts.

Facts are redacted before they touch disk. The scanner version is stored inside each entry, so a scanner
upgrade recomputes instead of reusing old facts.
"""
import json
from pathlib import Path

from redact import redact_obj


def facts(cache_dir: Path | None, sha256: str, version: str, compute):
    if cache_dir is None:
        return compute()
    path = cache_dir / f"{sha256}.json"
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        if entry["scan_version"] == version:
            return entry["facts"]
    except (OSError, ValueError, KeyError):
        pass
    fresh, _ = redact_obj(compute())
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"scan_version": version, "facts": fresh}), encoding="utf-8", newline="\n")
    return fresh
