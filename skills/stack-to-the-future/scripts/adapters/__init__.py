"""Framework adapters add facts static analysis misses. Every module here exposing ADAPTER is used; no registry."""
import importlib
import pkgutil

KEYS = ("calls", "entry_points", "permission_branches", "status_columns")


def load() -> list:
    # Imported lazily: adapter modules import from scan, which imports this package.
    mods = (importlib.import_module(f"{__name__}.{m.name}") for m in pkgutil.iter_modules(__path__))
    return sorted((m.ADAPTER for m in mods if hasattr(m, "ADAPTER")), key=lambda a: a.name)


def run(project) -> dict:
    """Run every adapter that applies and merge their facts. relabel: entry id -> fields; hints: path -> layer hint."""
    out = {k: [] for k in KEYS} | {"relabel": {}, "hints": {}, "applied": []}
    for adapter in load():
        if adapter.applies(project):
            facts = adapter.extract(project)
            for k in KEYS:
                out[k] += facts.get(k, [])
            out["relabel"].update(facts.get("relabel", {}))
            out["hints"].update(facts.get("hints", {}))
            out["applied"].append(adapter.name)
    return out
