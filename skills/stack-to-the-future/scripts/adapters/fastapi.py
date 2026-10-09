"""FastAPI: full route paths from router prefixes, Depends chains as calls and access checks, middleware, BackgroundTasks."""
import re

from adapters._common import descendants, edge, files_mentioning, kwarg, line, parse, positional, qualname, string, text
from scan import ROUTE_RX

DEPENDS_RX = re.compile(r"\b(?:Depends|Security)\(\s*([\w.]+)")
GUARD_RX = re.compile(r"\b(?:40[13]|HTTP_40[13]\w*|UNAUTHORIZED|FORBIDDEN)\b")
ROUTER_TYPES = {"APIRouter", "FastAPI"}


def prefix_of(node) -> str:
    if node is None:
        return ""
    literal = string(node)
    # ponytail: non-literal prefixes (settings.API_V1_STR) shown as {API_V1_STR}; resolve settings defaults if it matters
    return literal if literal is not None else "{" + text(node).rsplit(".", 1)[-1] + "}"


def own_qual(defn) -> str:
    outer, name = qualname(defn), text(defn.child_by_field_name("name"))
    return name if outer == "<module>" else f"{outer}.{name}"


class FastAPIAdapter:
    name = "fastapi"

    def applies(self, project) -> bool:
        return project.uses("fastapi")

    def extract(self, project) -> dict:
        routers = {}   # (file, var) -> {prefix, deps: [(file, expr)]}
        includes = []  # (file, parent expr, child expr, prefix, deps)
        aliases = {}   # (file, name) -> [expr]   e.g. CurrentUser = Annotated[User, Depends(get_current_user)]
        fn_deps = {}   # (file, qual) -> [(file, expr, line, via_alias)]
        middleware, tasks = [], []

        for path in files_mentioning(project, "fastapi"):
            for n in descendants(parse(project, path)):
                if n.type == "assignment" and n.parent.parent.type == "module":
                    left, right = n.child_by_field_name("left"), n.child_by_field_name("right")
                    if left.type != "identifier" or right is None:
                        continue
                    if right.type == "call" and text(right.child_by_field_name("function")).rsplit(".", 1)[-1] in ROUTER_TYPES:
                        deps = kwarg(right, "dependencies")
                        routers[(path, text(left))] = {"prefix": prefix_of(kwarg(right, "prefix")),
                                                       "deps": [(path, e) for e in DEPENDS_RX.findall(text(deps) if deps else "")]}
                    elif DEPENDS_RX.search(text(right)):
                        aliases[(path, text(left))] = DEPENDS_RX.findall(text(right))
                elif n.type == "call":
                    fn = text(n.child_by_field_name("function"))
                    args = positional(n)
                    if fn.endswith(".include_router") and args:
                        deps = kwarg(n, "dependencies")
                        includes.append((path, fn[:-len(".include_router")], text(args[0]), prefix_of(kwarg(n, "prefix")),
                                         [(path, e) for e in DEPENDS_RX.findall(text(deps) if deps else "")]))
                    elif fn.endswith(".add_middleware") and args:
                        middleware.append((path, text(args[0])))
                    elif fn.endswith(".add_task") and args:
                        tasks.append((path, qualname(n), line(n), text(args[0])))
                elif n.type == "function_definition":
                    qual, found = own_qual(n), []
                    for p in n.child_by_field_name("parameters").named_children:
                        found += [(path, e, line(p), False) for e in DEPENDS_RX.findall(text(p))]
                        annotation = p.child_by_field_name("type")
                        if annotation is not None and re.fullmatch(r"[\w.]+", text(annotation)):
                            found.append((path, text(annotation), line(p), True))
                    if n.parent.type == "decorated_definition":
                        for d in (c for c in n.parent.children if c.type == "decorator"):
                            if ROUTE_RX.match(text(d)):
                                found += [(path, e, line(d), False) for e in DEPENDS_RX.findall(text(d))]
                            elif re.match(r"@\s*[\w.]+\.middleware\(", text(d)):
                                middleware.append((path, qual))
                    if found:
                        fn_deps[(path, qual)] = found

        def callable_target(path, expr):
            t = project.resolve(path, expr)
            return t if t and project.symbols[t[0]][t[1]]["kind"] != "assignment" else None

        def deps_of(key) -> list:
            """[(target, expr, line)] a function depends on, expanding Annotated aliases."""
            out = []
            for path, expr, ln, via_alias in fn_deps.get(key, []):
                if via_alias:
                    alias = project.resolve(path, expr)
                    out += [(t, e, ln) for e in aliases.get(alias, []) if (t := callable_target(alias[0], e))]
                elif t := callable_target(path, expr):
                    out.append((t, expr, ln))
            return out

        sources = {}

        def guards(target, seen=()) -> bool:
            """Does this dependency refuse callers (401/403) or branch on roles/permissions, directly or via its own deps?"""
            if target in seen:
                return False
            sym = project.symbols[target[0]][target[1]]
            lines = sources.setdefault(target[0], project.source(target[0]).decode("utf-8", "replace").splitlines())
            body = "\n".join(lines[sym["start_line"] - 1:sym["end_line"]])
            if GUARD_RX.search(body) or any(b["function"] == target[1] for b in project.facts[target[0]]["permission_branches"]):
                return True
            return any(guards(t, (*seen, target)) for t, _, _ in deps_of(target))

        resolved_includes = sorted(
            (parent, child, prefix, deps) for path, p_expr, c_expr, prefix, deps in includes
            if (parent := project.resolve(path, p_expr)) in routers and (child := project.resolve(path, c_expr)) in routers)

        def chain(key, seen=()):
            """(prefix, [(file, expr)] dependencies) accumulated from the app down to this router."""
            own = routers[key]
            parents = [i for i in resolved_includes if i[1] == key and i[0] not in seen]
            if not parents:  # ponytail: a router mounted twice keeps its first mount only
                return own["prefix"], own["deps"]
            parent, _, prefix, deps = parents[0]
            p_prefix, p_deps = chain(parent, (*seen, key))
            return p_prefix + prefix + own["prefix"], p_deps + deps + own["deps"]

        facts = {"calls": [], "entry_points": [], "relabel": {}, "permission_branches": [], "hints": {}}
        for (path, qual), _ in fn_deps.items():
            facts["calls"] += [edge(path, qual, ln, t) for t, _, ln in deps_of((path, qual))]

        for ep in project.entry_points:
            if ep["kind"] != "api_route" or not ep.get("router"):
                continue
            key = project.resolve(ep["file"], ep["router"])
            prefix, router_deps = chain(key) if key in routers else ("", [])
            full = prefix + ep["path"]
            facts["relabel"][ep["id"]] = {"label": f"{ep['label'].split(' ', 1)[0]} {full or '/'}", "path": full}
            inherited = [(t, e, ep["start_line"]) for f, e in router_deps if (t := callable_target(f, e))]
            facts["calls"] += [edge(ep["file"], ep["symbol"], ln, t) for t, _, ln in inherited]
            seen = set()
            for t, expr, ln in deps_of((ep["file"], ep["symbol"])) + inherited:
                if expr not in seen and guards(t):
                    seen.add(expr)
                    facts["permission_branches"].append({"file": ep["file"], "function": ep["symbol"], "line": ln,
                                                         "test": f"Depends({expr})"})

        for path, caller, ln, expr in tasks:
            if t := callable_target(path, expr):
                sym = project.symbols[t[0]][t[1]]
                facts["calls"].append(edge(path, caller, ln, t))
                facts["entry_points"].append({"kind": "background_job", "label": t[1], "file": t[0], "symbol": t[1],
                                              "start_line": sym["start_line"], "end_line": sym["end_line"], "id": f"{t[0]}::{t[1]}"})

        by_file = {}
        for path, expr in middleware:
            if t := project.resolve(path, expr):
                by_file.setdefault(t[0], set()).add(t[1])
        for path, names in by_file.items():
            defs = {n for n, s in project.symbols.get(path, {}).items() if s["kind"] in ("function", "class") and "." not in n}
            if defs and defs <= names:  # the file only holds middleware: plumbing, not business
                facts["hints"][path] = {"hint": "foundation", "group": "wiring"}
        return facts


ADAPTER = FastAPIAdapter()
