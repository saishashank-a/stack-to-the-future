"""Group a scan into modules and workflow skeletons. Deterministic hints: Claude names them, the human corrects them."""
import re
from itertools import combinations

import networkx as nx

import graph

CODE = {"python", "typescript", "javascript"}


def module_folders(paths: list[str]) -> list[str]:
    """Top-level package or app folder. Descend through single-folder wrappers (src/, a lone package), then split."""
    base = ""
    while True:
        children = sorted({p[len(base):].split("/")[0] for p in paths if p.startswith(base) and "/" in p[len(base):]})
        if len(children) != 1:
            break
        base += children[0] + "/"
    if is_next_app(base, paths):
        return next_app_folders(base, paths)
    if not children:
        return [base.rstrip("/") or "."]
    return [f for c in children
            for f in (next_app_folders(base + c + "/", paths) if is_next_app(base + c + "/", paths) else [base + c])]


NEXT_ROOT = re.compile(r"(page|layout)\.(tsx|ts|jsx|js)")


def is_next_app(folder: str, paths: list[str]) -> bool:
    return (folder.rstrip("/").rsplit("/", 1)[-1] == "app"
            and any(p.startswith(folder) and NEXT_ROOT.fullmatch(p[len(folder):]) for p in paths))


def next_app_folders(base: str, paths: list[str]) -> list[str]:
    """Next.js App Router: a module per first URL segment. Route groups `(x)` and `api/` are see-through;
    root files and `_private` folders form the app's own module, listed last so deeper folders claim files first."""
    def folders_under(prefix):
        return sorted({p[len(prefix):].split("/")[0] for p in paths if p.startswith(prefix) and "/" in p[len(prefix):]})

    found, todo = [], [base]
    while todo:
        prefix = todo.pop(0)
        for c in folders_under(prefix):
            if (c.startswith("(") and c.endswith(")")) or c == "api":
                todo.append(prefix + c + "/")
            elif not c.startswith("_"):
                found.append(prefix + c)
    return sorted(found) + [base.rstrip("/") or "."]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "root"


def cluster(scan: dict, draft_limit: int = 8) -> dict:
    files = {f["path"]: f for f in scan["files"]}
    code = [p for p, f in files.items() if f["hint"] != "ignored" and f["language"] in CODE]
    folders = module_folders(code)
    leaves = [slug(f.rsplit("/", 1)[-1]) for f in folders]
    ids = {f: (leaf if leaves.count(leaf) == 1 else slug(f)) for f, leaf in zip(folders, leaves)}
    owner = {p: next((ids[f] for f in folders if f == "." or p.startswith(f + "/")), None) for p in code}
    calls, imports = graph.call_graph(scan["calls"]), graph.import_graph(scan["imports"])

    def file_of(node):
        return node.split("::", 1)[0]

    modules, workflows = [], []
    for folder in folders:
        mid = ids[folder]
        mfiles = sorted(p for p, m in owner.items() if m == mid)
        eps = [e for e in scan["entry_points"] if owner.get(e["file"]) == mid]
        importers = sorted({owner.get(src) for f in mfiles if f in imports for src in imports.predecessors(f)} - {None, mid})
        if all(files[p]["hint"] == "foundation" for p in mfiles):
            role = "foundation"
        elif not eps and len(importers) >= 2:
            role = "shared"
        else:
            role = "business"
        module = {"id": mid, "folder": folder, "role": role, "files": mfiles, "entry_points": [e["id"] for e in eps],
                  "imported_by": importers, "workflows": []}
        if role == "business":
            for skeleton in skeletons(scan, eps, mid, calls, file_of):
                skeleton["id"] = f"{mid}/w{len(module['workflows']) + 1}"
                module["workflows"].append(skeleton["id"])
                workflows.append(skeleton)
        modules.append(module)

    roles = {m["id"]: m["role"] for m in modules}
    shared = {p for m in modules if m["role"] == "shared" for p in m["files"] if files[p]["hint"] == "business"}
    for p in code:
        users = {owner.get(src) for src in (imports.predecessors(p) if p in imports else [])}
        if files[p]["hint"] == "business" and len({u for u in users if roles.get(u) == "business"} - {owner[p]}) >= 2:
            shared.add(p)

    attached = {i for w in workflows for i in w["incomplete"]}
    business = sorted((m for m in modules if m["role"] == "business"), key=lambda m: (-len(m["entry_points"]), m["id"]))
    foundation = {}
    for p, f in files.items():
        if f["hint"] == "foundation":
            foundation.setdefault(f["group"], []).append(p)
    return {
        "modules": modules,
        "workflows": workflows,
        "shared_candidates": sorted(shared),
        "foundation": {g: sorted(ps) for g, ps in sorted(foundation.items())},
        "unassigned": sorted(p for p in code if owner[p] is None and files[p]["hint"] == "business"),
        "loose_incomplete": [ref(i) for i in scan["incomplete"] if ref(i) not in attached],
        "draft_order": [m["id"] for m in business],
        "draft_now": [m["id"] for m in business[:draft_limit]],
    }


def ref(item: dict) -> str:
    return f"{item['file']}:{item['line']}"


def skeletons(scan, eps, mid, calls, file_of):
    """One skeleton per group of entry points that live in the same file, reach each other, or drive the same status machine.

    ponytail: file-level grouping; a single-file app gets one skeleton until Claude splits it at draft time.
    Sharing helpers is deliberately not a link: common crud/deps code chained every route into one blob.
    """
    node = {e["id"]: graph.node(e["file"], e["symbol"]) for e in eps}
    reach = {i: graph.reachable(calls, n) | {n} for i, n in node.items()}
    enums = {i: {m["enum"] for m in scan["status_machines"] for t in m["transitions"]
                 if graph.node(t["file"], t["function"]) in r} for i, r in reach.items()}

    g = nx.Graph()
    g.add_nodes_from(node)
    for a, b in combinations(node, 2):
        if file_of(node[a]) == file_of(node[b]) or node[a] in reach[b] or node[b] in reach[a] or enums[a] & enums[b]:
            g.add_edge(a, b)

    out = []
    for group in sorted((sorted(c) for c in nx.connected_components(g)), key=lambda c: c[0]):
        nodes = set().union(*(reach[i] for i in group))
        touched = set().union(*(enums[i] for i in group))
        incomplete = [ref(i) for i in scan["incomplete"]
                      if graph.node(i["file"], i.get("symbol") or "") in nodes
                      or (i["kind"] == "missing_transition" and i["symbol"].split(".")[0] in touched)]
        out.append({
            "module": mid,
            "entry_points": group,
            "files": sorted({file_of(n) for n in nodes}),
            "symbols": sorted(nodes),
            "status_machines": sorted(touched),
            "permission_branches": [ref(b) for b in scan["permission_branches"] if graph.node(b["file"], b["function"]) in nodes],
            "incomplete": incomplete,
        })
    return out
