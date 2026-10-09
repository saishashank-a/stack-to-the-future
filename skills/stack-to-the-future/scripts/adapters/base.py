"""The adapter contract (PLAN section 7). Facts use the scan.json shapes."""
from typing import Protocol


class Adapter(Protocol):
    name: str

    def applies(self, project) -> bool:
        """Cheap check, e.g. the framework is imported anywhere in the repo."""

    def extract(self, project) -> dict:
        """Return any of:
        calls: [{file, caller, line, target_file, target_symbol}]  extra resolved call edges
        entry_points: [scan entry point]                           new entry points (deduped by id)
        relabel: {entry_point_id: {label, path, also_at?}}         fix labels in place; also_at = other mount paths
        permission_branches: [{file, function, line, test}]
        status_columns: [{file, model, field, line, enum_file, enum}]
        incomplete: [{file, kind, line, end_line, symbol, text?}]   for files the Python scanner does not parse
        hints: {path: {hint, group}}                               override a file's layer hint
        """
