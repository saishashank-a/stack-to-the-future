"""Deterministic static scan of a repository. No LLM, no network, no string literal values stored.

Produces the facts the atlas is built from: files, symbols, imports, resolved calls, entry points,
status machines, role/permission branches, data models, incomplete code and foundation candidates.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import tree_sitter_python
from tree_sitter import Language, Parser

import adapters
import cache
import graph
from redact import is_secret_file, redact_obj

SCAN_VERSION = "0.1"
PARSER = Parser(Language(tree_sitter_python.language()))

SKIP_DIRS = {".git", ".hg", ".svn", ".atlas", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
             ".pytest_cache", ".ruff_cache", ".tox", "dist", "build", "site-packages", ".next", ".idea", ".vscode"}
LANGUAGES = {".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".jsx": "javascript",
             ".md": "markdown", ".toml": "toml", ".json": "json", ".yml": "yaml", ".yaml": "yaml", ".txt": "text",
             ".cfg": "ini", ".ini": "ini", ".html": "html", ".css": "css", ".sql": "sql", ".sh": "shell"}
CODE_LANGUAGES = {"python", "typescript", "javascript"}
TEST_DIRS = {"tests", "test", "__tests__", "docs"}
DEPENDENCY_FILES = ("requirements*.txt", "pyproject.toml", "Pipfile", "Pipfile.lock", "poetry.lock", "uv.lock",
                    "setup.py", "setup.cfg", "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml")
CONFIG_FILES = {"config.py", "settings.py", "conf.py", "configuration.py"}
DATABASE_FILES = {"database.py", "db.py", "session.py"}
DATABASE_CALLS = {"create_engine", "create_async_engine", "sessionmaker", "async_sessionmaker", "declarative_base"}
WIRING_FILES = {"main.py", "app.py", "wsgi.py", "asgi.py", "manage.py", "worker.py", "celery.py", "__main__.py"}

ROUTE_RX = re.compile(r"^@\s*([\w.]+)\.(get|post|put|patch|delete|head|options|route|api_route|websocket)\s*\((.*)\)\s*$", re.S)
JOB_RX = re.compile(r"^@\s*(?:[\w.]+\.)?(task|shared_task|periodic_task|actor|job)\b(?:\s*\((.*)\))?\s*$", re.S)
CLI_RX = re.compile(r"^@\s*[\w.]+\.(command|group)\b(?:\s*\((.*)\))?\s*$", re.S)
FIRST_STRING = re.compile(r"""^\s*[rbuf]*(['"])(.*?)\1""")
NAME_KW = re.compile(r"""\bname\s*=\s*(['"])(.*?)\1""")
METHODS_KW = re.compile(r"""methods\s*=\s*[\[(]([^\])]*)""")
TODO_RX = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
PERMISSION_RX = re.compile(r"\b(roles?|is_admin|is_staff|is_superuser|is_owner|owner_id|has_perm\w*|has_role|"
                           r"permissions?|scopes?|can_\w+|manager_id|admin)\b", re.I)
STATUS_ATTRS = {"status", "state", "stage", "phase"}
STATUS_ENUM_RX = re.compile(r"status|state|stage|phase", re.I)
MODEL_BASES = {"DeclarativeBase": "orm", "Base": "orm", "Model": "orm", "db.Model": "orm", "models.Model": "orm",
               "SQLModel": "schema", "Document": "orm", "BaseModel": "schema", "TypedDict": "schema"}


# ---------------------------------------------------------------- files

def list_files(root: Path) -> list[str]:
    """Repo-relative POSIX paths. Uses git (respects .gitignore) when available, else a filtered walk."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             capture_output=True, check=True).stdout.decode()
        paths = [p for p in out.split("\0") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        paths = []
        for d, dirs, names in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            paths += [Path(d, n).relative_to(root).as_posix() for n in names]
    return sorted(p for p in paths if not SKIP_DIRS & set(p.split("/")[:-1]) and (root / p).is_file())


def language(path: str, data: bytes) -> str:
    if b"\0" in data[:8000]:
        return "binary"
    name = path.rsplit("/", 1)[-1]
    if is_secret_file(path):
        return "secret"
    if fnmatch.fnmatch(name, "requirements*.txt"):
        return "requirements"
    return LANGUAGES.get(Path(name).suffix, "other")


# ---------------------------------------------------------------- per-file analysis (pure: bytes in, facts out)

def analyze_python(src: bytes) -> dict:
    tree = PARSER.parse(src)
    f = {k: [] for k in ("symbols", "imports", "calls", "status_sets", "status_checks", "defaults",
                         "permission_branches", "incomplete", "main_guards", "cli_parsers")}
    f["parse_errors"] = tree.root_node.has_error

    def text(n):
        return n.text.decode("utf-8", "replace")

    def line(n):
        return n.start_point.row + 1

    def define(defn, outer, decorators, prefix, func):
        name = text(defn.child_by_field_name("name"))
        qual = f"{func}.{name}" if func else prefix + name
        body = defn.child_by_field_name("body")
        sym = {"name": qual, "start_line": line(outer), "end_line": outer.end_point.row + 1, "decorators": decorators}
        is_class = defn.type == "class_definition"
        for c in defn.children:  # tree-sitter hangs a comment on the first body line off the def, not the block
            if c.type == "comment":
                handle(c, qual + ".", func if is_class else qual)
        if is_class:
            supers = defn.child_by_field_name("superclasses")
            args = supers.named_children if supers else []
            sym.update(kind="class", bases=[text(a) for a in args if a.type != "keyword_argument"])
            if any(a.type == "keyword_argument" and re.fullmatch(r"table\s*=\s*True", text(a)) for a in args):
                sym["table"] = True  # SQLModel: only table=True classes are stored; the rest are schemas
            f["symbols"].append(sym)
            walk(body, qual + ".", func)
            return
        sym["kind"] = "method" if prefix and not func else "function"
        f["symbols"].append(sym)
        if not any(re.search(r"abstractmethod|overload", d) for d in decorators):
            raises = [n for n in descendants(body) if n.type == "raise_statement" and "NotImplementedError" in text(n)]
            if raises:
                f["incomplete"].append({"kind": "not_implemented", "line": line(raises[0]), "end_line": raises[0].end_point.row + 1, "symbol": qual})
            elif all(is_placeholder(s) for s in body.named_children if s.type != "comment"):
                f["incomplete"].append({"kind": "stub", "line": line(outer), "end_line": sym["end_line"], "symbol": qual})
        walk(body, qual + ".", qual)

    def is_placeholder(stmt):
        if stmt.type == "pass_statement":
            return True
        return stmt.type == "expression_statement" and len(stmt.named_children) == 1 and stmt.named_children[0].type in ("string", "ellipsis")

    def handle(n, prefix, func):
        t = n.type
        if t == "assignment":
            left, right = n.child_by_field_name("left"), n.child_by_field_name("right")
            if func is None and left.type == "identifier":
                f["symbols"].append({"name": prefix + text(left), "kind": "assignment", "start_line": line(n), "end_line": n.end_point.row + 1})
                for kw in (d for d in descendants(n) if d.type == "keyword_argument"):
                    value = kw.child_by_field_name("value")
                    if text(kw.child_by_field_name("name")) == "default" and value.type == "attribute":
                        f["defaults"].append({"value": text(value), "line": line(kw)})
            elif func and right is not None and left.type == "attribute" and right.type == "attribute" \
                    and text(left.child_by_field_name("attribute")) in STATUS_ATTRS:
                f["status_sets"].append({"function": func, "value": text(right), "line": line(n)})
        elif t == "comparison_operator" and func:
            operands = n.named_children
            if any(o.type == "attribute" and text(o.child_by_field_name("attribute")) in STATUS_ATTRS for o in operands):
                values = [text(a) for o in operands for a in [o, *descendants(o)]
                          if a.type == "attribute" and text(a.child_by_field_name("attribute")) not in STATUS_ATTRS
                          and a.parent.type != "attribute"]
                f["status_checks"].append({"function": func, "values": values, "line": line(n)})
        elif t in ("if_statement", "elif_clause"):
            cond = text(n.child_by_field_name("condition"))
            if PERMISSION_RX.search(cond):
                f["permission_branches"].append({"function": func or "<module>", "line": line(n), "test": cond})
            if func is None and not prefix and "__name__" in cond and "__main__" in cond:
                f["main_guards"].append(line(n))
        elif t == "call":
            callee = text(n.child_by_field_name("function"))
            f["calls"].append({"caller": func or "<module>", "callee": callee, "line": line(n)})
            if callee.endswith(".add_parser"):
                m = FIRST_STRING.match(text(n.child_by_field_name("arguments"))[1:])
                f["cli_parsers"].append({"label": m.group(2) if m else callee, "function": func or "<module>", "line": line(n)})
        elif t == "comment" and TODO_RX.search(text(n)):
            f["incomplete"].append({"kind": "todo", "line": line(n), "end_line": line(n), "symbol": func, "text": text(n).lstrip("# ").strip()})
        elif t == "import_statement":
            for c in n.named_children:
                name = c.child_by_field_name("name") if c.type == "aliased_import" else c
                alias = c.child_by_field_name("alias") if c.type == "aliased_import" else None
                f["imports"].append({"kind": "import", "module": text(name), "asname": alias and text(alias), "level": 0, "line": line(n)})
        elif t == "import_from_statement":
            mod = n.child_by_field_name("module_name")
            level = 0
            module = text(mod)
            if mod.type == "relative_import":
                prefix_node = next(c for c in mod.children if c.type == "import_prefix")
                level = len(text(prefix_node))
                module = module[level:]
            names = []
            for c in n.children_by_field_name("name"):
                if c.type == "aliased_import":
                    names.append([text(c.child_by_field_name("name")), text(c.child_by_field_name("alias"))])
                else:
                    names.append([text(c), None])
            if any(c.type == "wildcard_import" for c in n.children):
                names.append(["*", None])
            f["imports"].append({"kind": "from", "module": module, "names": names, "level": level, "line": line(n)})

    def walk(node, prefix, func):
        for child in node.children:
            if child.type == "decorated_definition":
                define(child.child_by_field_name("definition"), child,
                       [text(d) for d in child.children if d.type == "decorator"], prefix, func)
            elif child.type in ("function_definition", "class_definition"):
                define(child, child, [], prefix, func)
            else:
                handle(child, prefix, func)
                walk(child, prefix, func)

    walk(tree.root_node, "", None)
    return f


def descendants(node):
    for c in node.children:
        yield c
        yield from descendants(c)


# ---------------------------------------------------------------- cross-file resolution

class Project:
    def __init__(self, facts: dict[str, dict], root: Path | None = None, paths: list[str] = ()):
        self.facts, self.root, self.paths = facts, root, list(paths)
        self.entry_points: list[dict] = []
        self.symbols = {p: {s["name"]: s for s in f["symbols"]} for p, f in facts.items()}
        self.full, suffix = {}, {}
        for path in facts:
            parts = path[:-3].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            if parts:
                self.full[".".join(parts)] = path
            for i in range(1, len(parts)):
                suffix.setdefault(".".join(parts[i:]), set()).add(path)
        self.suffix = {k: next(iter(v)) for k, v in suffix.items() if len(v) == 1}
        self.bindings = {p: self._bindings(p) for p in facts}

    def uses(self, package: str) -> bool:
        return any(not i["level"] and i["module"].split(".")[0] == package for f in self.facts.values() for i in f["imports"])

    def source(self, path: str) -> bytes:
        return (self.root / path).read_bytes()

    def module_file(self, dotted: str) -> str | None:
        if not dotted or ("." not in dotted and dotted in sys.stdlib_module_names):
            return None
        return self.full.get(dotted) or self.suffix.get(dotted)

    def _bindings(self, path: str) -> dict:
        package = path.split("/")[:-1]
        table = {}
        for imp in self.facts[path]["imports"]:
            if imp["kind"] == "import":
                if imp["asname"]:
                    table[imp["asname"]] = ("module", imp["module"])
                else:
                    head = imp["module"].split(".")[0]
                    table[head] = ("module", head)
                continue
            if imp["level"]:
                up = imp["level"] - 1
                if up > len(package):
                    continue
                base = ".".join(package[:len(package) - up] + ([imp["module"]] if imp["module"] else []))
            else:
                base = imp["module"]
            for name, asname in imp["names"]:
                if name == "*":
                    continue
                sub = f"{base}.{name}" if base else name
                table[asname or name] = ("module", sub) if self.module_file(sub) else ("symbol", base, name)
        return table

    def pick(self, path: str, parts: list[str]) -> tuple[str, str] | None:
        table = self.symbols.get(path, {})
        for i in range(len(parts), 0, -1):
            if ".".join(parts[:i]) in table:
                return path, ".".join(parts[:i])
        return None

    def resolve(self, path: str, dotted: str, caller: str | None = None) -> tuple[str, str] | None:
        """Map a dotted name used in `path` to (file, qualified symbol) inside the repo, if it is one."""
        if not re.fullmatch(r"[\w.]+", dotted):
            return None
        head, *rest = dotted.split(".")
        if head in ("self", "cls") and caller and "." in caller:
            return self.pick(path, [caller.rsplit(".", 1)[0], *rest])
        if head in self.symbols[path]:
            return self.pick(path, [head, *rest])
        binding = self.bindings[path].get(head)
        if binding is None:
            return None
        if binding[0] == "symbol":
            target = self.module_file(binding[1])
            return target and self.pick(target, [binding[2], *rest])
        full = binding[1].split(".") + rest
        for i in range(len(full), 0, -1):
            target = self.module_file(".".join(full[:i]))
            if target:
                return self.pick(target, full[i:]) if full[i:] else None
        return None


# ---------------------------------------------------------------- the scan

def scan(root: str | Path, cache_dir: Path | None = None) -> dict:
    root = Path(root).resolve()
    files, facts = [], {}
    for path in list_files(root):
        data = (root / path).read_bytes()  # secret files are hashed for change detection, never parsed or stored
        entry = {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "language": language(path, data),
                 "loc": data.count(b"\n")}
        if entry["language"] == "python":
            facts[path] = cache.facts(cache_dir, entry["sha256"], SCAN_VERSION, lambda: analyze_python(data))
            entry["parse_errors"] = facts[path].pop("parse_errors")
        files.append(entry)

    project = Project(facts, root, [e["path"] for e in files])
    project.entry_points = entry_points(project)
    extra = adapters.run(project)
    for e in extra["entry_points"]:
        if all(e["id"] != x["id"] for x in project.entry_points):
            project.entry_points.append(e)
    for e in project.entry_points:
        e.update(extra["relabel"].get(e["id"], {}))
    calls = list(extra["calls"])
    for path, f in facts.items():
        for c in f["calls"]:
            target = project.resolve(path, c["callee"], c["caller"])
            if target and project.symbols[target[0]][target[1]]["kind"] != "assignment":  # skip `router.post`, `app.include_router`
                calls.append({"file": path, "caller": c["caller"], "line": c["line"], "target_file": target[0], "target_symbol": target[1]})
    calls_g = graph.call_graph(calls)

    symbols = [{"file": p, **s} for p, f in facts.items() for s in f["symbols"]]
    enums = enum_classes(project)
    machines = status_machines(project, enums, calls_g)
    for m in machines:
        columns = [{k: c[k] for k in ("file", "model", "field", "line")} for c in extra["status_columns"]
                   if (c["enum_file"], c["enum"]) == (m["file"], m["enum"])]
        if columns:
            m["columns"] = columns
    incomplete = [{"file": p, **i} for p, f in facts.items() for i in f["incomplete"]]
    for m in machines:
        for state in m["missing"]:
            member = project.symbols[m["file"]][f"{m['enum']}.{state}"]
            incomplete.append({"file": m["file"], "kind": "missing_transition", "line": member["start_line"],
                               "end_line": member["end_line"], "symbol": f"{m['enum']}.{state}",
                               "text": f"{m['enum']}.{state} is never reached"})

    result = {
        "scan_version": SCAN_VERSION,
        "root": root.name,
        "files": [dict(e, **(extra["hints"].get(e["path"]) or hint(e, facts.get(e["path"])))) for e in files],
        "external_imports": sorted({i["module"].split(".")[0] for p, f in facts.items() for i in f["imports"]
                                    if not i["level"] and i["module"] and not project.module_file(i["module"])}
                                   - sys.stdlib_module_names),
        "symbols": sorted(symbols, key=lambda s: (s["file"], s["start_line"], s["name"])),
        "imports": sorted(({"file": p, "line": i["line"], "module": "." * i["level"] + i["module"],
                            "target": import_target(project, p, i)} for p, f in facts.items() for i in f["imports"]),
                          key=lambda i: (i["file"], i["line"], i["module"])),
        "calls": sorted({tuple(sorted(c.items())): c for c in calls}.values(),
                        key=lambda c: (c["file"], c["line"], c["caller"], c["target_file"], c["target_symbol"])),
        "entry_points": sorted(project.entry_points, key=lambda e: (e["file"], e["start_line"], e["id"])),
        "status_machines": [{k: v for k, v in m.items() if k != "missing"} for m in machines],
        "permission_branches": sorted([{"file": p, **b} for p, f in facts.items() for b in f["permission_branches"]]
                                      + extra["permission_branches"], key=lambda b: (b["file"], b["line"], b["test"])),
        "models": models(project),
        "incomplete": sorted(incomplete, key=lambda i: (i["file"], i["line"])),
    }
    result, _ = redact_obj(result)
    result["redactions"] = json.dumps(result).count("[REDACTED:")  # same count whether facts came from cache or not
    return result


def import_target(project: Project, path: str, imp: dict) -> str | None:
    if imp["kind"] == "import":
        return project.module_file(imp["module"])
    package = path.split("/")[:-1]
    up = imp["level"] - 1 if imp["level"] else 0
    base = ".".join(package[:len(package) - up] + ([imp["module"]] if imp["module"] else [])) if imp["level"] else imp["module"]
    return project.module_file(base)


def entry_points(project: Project) -> list[dict]:
    found = []
    for path, table in project.symbols.items():
        for sym in table.values():
            for dec in sym.get("decorators", []):
                if m := ROUTE_RX.match(dec):
                    route = FIRST_STRING.match(m.group(3))
                    methods = [x.strip(" '\"").upper() for x in METHODS_KW.search(m.group(3)).group(1).split(",")] \
                        if m.group(2) in ("route", "api_route") and METHODS_KW.search(m.group(3)) else \
                        ["GET"] if m.group(2) == "route" else [m.group(2).upper()]
                    path_text = route.group(2) if route else ""
                    found.append({"kind": "api_route", "label": f"{'|'.join(methods)} {path_text or '/'}", "path": path_text,
                                  "router": m.group(1), "file": path, "symbol": sym["name"]})
                elif m := JOB_RX.match(dec):
                    name = NAME_KW.search(m.group(2) or "")
                    found.append({"kind": "background_job", "label": name.group(2) if name else sym["name"], "file": path, "symbol": sym["name"]})
                elif m := CLI_RX.match(dec):
                    name = NAME_KW.search(m.group(2) or "") or FIRST_STRING.match(m.group(2) or "")
                    found.append({"kind": "cli_command", "label": name.group(2) if name else sym["name"], "file": path, "symbol": sym["name"]})
        for ln in project.facts[path]["main_guards"]:
            found.append({"kind": "cli_command", "label": f"python {path}", "file": path, "symbol": "<module>", "line": ln})
        for p in project.facts[path]["cli_parsers"]:
            found.append({"kind": "cli_command", "label": p["label"], "file": path, "symbol": p["function"], "line": p["line"]})
    for e in found:
        sym = project.symbols[e["file"]].get(e["symbol"])
        e["start_line"] = sym["start_line"] if sym else e.pop("line")
        e["end_line"] = sym["end_line"] if sym else e["start_line"]
        e.pop("line", None)
        e["id"] = f"{e['file']}::{e['symbol']}" + ("" if sym else f"@{e['start_line']}")
    return sorted(found, key=lambda e: (e["file"], e["start_line"]))


def enum_classes(project: Project) -> dict[tuple[str, str], list[str]]:
    """(file, class) -> member names, for every Enum subclass."""
    out = {}
    for path, table in project.symbols.items():
        for sym in table.values():
            if sym["kind"] == "class" and any(b.split(".")[-1].endswith("Enum") for b in sym["bases"]):
                prefix = sym["name"] + "."
                out[(path, sym["name"])] = [n[len(prefix):] for n, s in table.items()
                                            if n.startswith(prefix) and s["kind"] == "assignment"
                                            and "." not in n[len(prefix):] and not n[len(prefix):].startswith("_")]
    return out


def status_machines(project: Project, enums: dict, calls_g) -> list[dict]:
    def member(path, value):
        target = project.resolve(path, value.rsplit(".", 1)[0]) if "." in value else None
        return (target, value.rsplit(".", 1)[1]) if target in enums else (None, None)

    sets, checks, defaults = {}, {}, {}
    for path, f in project.facts.items():
        for s in f["status_sets"]:
            enum, state = member(path, s["value"])
            if enum:
                sets.setdefault(enum, []).append({"to": state, "file": path, "function": s["function"], "line": s["line"]})
        for c in f["status_checks"]:
            for v in c["values"]:
                enum, state = member(path, v)
                if enum:
                    checks.setdefault((enum, graph.node(path, c["function"])), set()).add(state)
        for d in f["defaults"]:
            enum, state = member(path, d["value"])
            if enum:
                defaults.setdefault(enum, set()).add(state)

    machines = []
    for enum, states in sorted(enums.items()):
        if not (STATUS_ENUM_RX.search(enum[1]) or enum in sets):
            continue
        transitions = []
        for t in sorted(sets.get(enum, []), key=lambda t: (t["file"], t["line"])):
            near = graph.neighbourhood(calls_g, graph.node(t["file"], t["function"]))
            sources = set().union(*(checks.get((enum, n), set()) for n in near)) - {t["to"]}
            transitions.append({"from": sorted(sources), **t})
        initial = sorted(defaults.get(enum, set()))
        reached = set(initial) | {t["to"] for t in transitions}
        machines.append({"file": enum[0], "enum": enum[1], "states": states, "initial": initial,
                         "transitions": transitions, "missing": [s for s in states if s not in reached]})
    return machines


def models(project: Project) -> list[dict]:
    def kind_of(path, sym, seen=()):
        if (path, sym["name"]) in seen:
            return None
        if any("dataclass" in d for d in sym.get("decorators", [])):
            return "dataclass"
        for base in sym["bases"]:
            target = project.resolve(path, base)
            if target and project.symbols[target[0]][target[1]]["kind"] == "class":
                if k := kind_of(target[0], project.symbols[target[0]][target[1]], (*seen, (path, sym["name"]))):
                    return k
            elif base in MODEL_BASES:
                return MODEL_BASES[base]
        return None

    out = []
    for path, table in project.symbols.items():
        for sym in table.values():
            if sym["kind"] != "class" or not (kind := kind_of(path, sym)):
                continue
            prefix = sym["name"] + "."
            fields = [n[len(prefix):] for n, s in table.items() if n.startswith(prefix) and s["kind"] == "assignment"
                      and "." not in n[len(prefix):] and not n[len(prefix):].startswith("_") and n[len(prefix):] != "model_config"]
            if kind == "schema" and (sym.get("table") or f"{sym['name']}.__tablename__" in table):
                kind = "orm"
            if fields:
                out.append({"file": path, "name": sym["name"], "kind": kind, "fields": fields,
                            "start_line": sym["start_line"], "end_line": sym["end_line"]})
    return sorted(out, key=lambda m: (m["file"], m["start_line"]))


def hint(entry: dict, f: dict | None) -> dict:
    """Layer hint for clustering: business, foundation (+group) or ignored. Claude and the human have the last word."""
    path, lang = entry["path"], entry["language"]
    name, parts = path.rsplit("/", 1)[-1], path.split("/")
    if lang == "secret":
        return {"hint": "foundation", "group": "secrets_loading"}
    if any(fnmatch.fnmatch(name, p) for p in DEPENDENCY_FILES):
        return {"hint": "foundation", "group": "dependencies"}
    if lang not in CODE_LANGUAGES or TEST_DIRS & set(parts[:-1]) or fnmatch.fnmatch(name, "test_*.py") \
            or fnmatch.fnmatch(name, "*_test.py") or name == "conftest.py":
        return {"hint": "ignored"}
    if f is None:
        return {"hint": "business"}
    tails = {c["callee"].rsplit(".", 1)[-1] for c in f["calls"]}
    defs = [s for s in f["symbols"] if s["kind"] in ("function", "class")]
    if name in CONFIG_FILES or any(b.endswith("BaseSettings") for s in f["symbols"] for b in s.get("bases", [])):
        return {"hint": "foundation", "group": "configuration"}
    if name in DATABASE_FILES or tails & DATABASE_CALLS:
        return {"hint": "foundation", "group": "database_setup"}
    if tails & {"load_dotenv", "dotenv_values"}:
        return {"hint": "foundation", "group": "secrets_loading"}
    if (name in WIRING_FILES and len(defs) <= 2) or (name == "__init__.py" and not defs):
        return {"hint": "foundation", "group": "wiring"}
    return {"hint": "business"}
