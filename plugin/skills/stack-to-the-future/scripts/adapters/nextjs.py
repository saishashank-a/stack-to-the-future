"""Next.js App Router: pages, route handlers, layouts and server actions. The only place TypeScript is parsed in v1."""
import json
import re

import tree_sitter_typescript
from tree_sitter import Language, Parser

from scan import TODO_RX

TSX = Parser(Language(tree_sitter_typescript.language_tsx()))
TS = Parser(Language(tree_sitter_typescript.language_typescript()))
SOURCE_EXTS = (".tsx", ".ts", ".jsx", ".js")
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
NOT_IMPLEMENTED_RX = re.compile(r"not\s*(yet\s*)?implemented", re.I)


def text(n) -> str:
    return n.text.decode("utf-8", "replace")


def next_roots(project) -> list[str]:
    """Folders ('' = repo root) whose package.json depends on next, or that hold a next.config.*."""
    roots = set()
    for path in project.paths:
        folder, _, name = path.rpartition("/")
        if name.startswith("next.config."):
            roots.add(folder)
        elif name == "package.json":
            try:
                pkg = json.loads(project.source(path))
            except ValueError:
                continue
            if "next" in {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}:
                roots.add(folder)
    return sorted(roots)


def route_path(folders: list[str]) -> str | None:
    """URL for a folder chain under app/. Route groups (x) and parallel slots @x vanish; private _x folders aren't routable."""
    parts = []
    for f in folders:
        if f.startswith("_"):
            return None
        if not (f.startswith("(") and f.endswith(")")) and not f.startswith("@"):
            parts.append(f)
    return "/" + "/".join(parts)


def parse(project, path):
    return (TS if path.endswith(".ts") else TSX).parse(project.source(path)).root_node


def exports(program) -> dict[str, tuple[int, int]]:
    """Exported name -> (start line, end line). 'default' for the default export."""
    out = {}
    for st in (n for n in program.named_children if n.type == "export_statement"):
        lines = (st.start_point.row + 1, st.end_point.row + 1)
        if any(c.type == "default" for c in st.children):
            out["default"] = lines
            continue
        decl = st.child_by_field_name("declaration")
        if decl is not None and decl.child_by_field_name("name") is not None:
            out[text(decl.child_by_field_name("name"))] = lines
        elif decl is not None:
            for v in (c for c in decl.named_children if c.type == "variable_declarator"):
                out[text(v.child_by_field_name("name"))] = lines
        for clause in (c for c in st.named_children if c.type == "export_clause"):
            for spec in clause.named_children:
                out[text(spec.child_by_field_name("alias") or spec.child_by_field_name("name"))] = lines
    return out


def use_server(program) -> bool:
    first = next((n for n in program.named_children if n.type != "comment"), None)
    return first is not None and first.type == "expression_statement" and text(first).strip("'\"; ") == "use server"


FUNCTIONS = ("function_declaration", "generator_function_declaration", "method_definition", "arrow_function",
             "function_expression")


def owner(n) -> str | None:
    """Name of the function holding this node: its declaration name, the variable it's assigned to, or 'default'."""
    while n is not None:
        if n.type in FUNCTIONS:
            name = n.child_by_field_name("name")
            if name is None and n.parent is not None and n.parent.type == "variable_declarator":
                name = n.parent.child_by_field_name("name")
            if name is not None:
                return text(name)
            if n.parent is not None and n.parent.type == "export_statement":
                return "default"
        n = n.parent
    return None


def incomplete(program) -> list[dict]:
    """TODO/FIXME comments, `throw new Error("not implemented")`, and named functions whose body is empty.
    Anonymous empty callbacks (`() => {}`) are deliberate no-ops, so they don't count."""
    out, todo = [], [program]
    while todo:
        n = todo.pop()
        todo.extend(n.children)
        start, end = n.start_point.row + 1, n.end_point.row + 1
        if n.type == "comment" and TODO_RX.search(text(n)):
            out.append({"kind": "todo", "line": start, "end_line": start, "symbol": owner(n),
                        "text": text(n).strip("/* \n").strip()})
        elif n.type == "throw_statement" and NOT_IMPLEMENTED_RX.search(text(n)):
            out.append({"kind": "not_implemented", "line": start, "end_line": end, "symbol": owner(n)})
        elif n.type in FUNCTIONS and (body := n.child_by_field_name("body")) is not None \
                and body.type == "statement_block" and all(c.type == "comment" for c in body.named_children):
            name = owner(n)
            if name and name != "constructor" and owner(n.parent) != name:
                out.append({"kind": "stub", "line": start, "end_line": end, "symbol": name})
    return sorted(out, key=lambda i: (i["line"], i["kind"]))


class NextJSAdapter:
    name = "nextjs"

    def applies(self, project) -> bool:
        return bool(next_roots(project))

    def extract(self, project) -> dict:
        facts, flagged = {"entry_points": [], "hints": {}, "incomplete": []}, set()

        def add(kind, label, file, symbol, lines, **extra):
            facts["entry_points"].append({"kind": kind, "label": label, **extra, "file": file, "symbol": symbol,
                                          "start_line": lines[0], "end_line": lines[1], "id": f"{file}::{symbol}"})

        for root in next_roots(project):
            base = f"{root}/" if root else ""
            apps = [f"{base}app/", f"{base}src/app/"]
            for path in (p for p in project.paths if p.startswith(base) and p.endswith(SOURCE_EXTS)):
                program = None
                app = next((a for a in apps if path.startswith(a)), None)
                if app:
                    folders, _, filename = path[len(app):].rpartition("/")
                    stem, url = filename.rsplit(".", 1)[0], route_path(folders.split("/") if folders else [])
                    if stem in ("layout", "template"):
                        facts["hints"][path] = {"hint": "foundation", "group": "wiring"}
                    elif url is not None and stem in ("page", "route"):
                        program = parse(project, path)
                        found = exports(program)
                        if stem == "page":
                            add("ui_page", url, path, "default", found.get("default", (1, 1)), path=url)
                        for method in (m for m in METHODS if m in found and stem == "route"):
                            add("api_route", f"{method} {url}", path, method, found[method], path=url)
                if program is None:
                    program = parse(project, path)
                if use_server(program):
                    for name, lines in sorted(exports(program).items()):
                        add("event_handler", f"server action {name}", path, name, lines)
                if path not in flagged:  # nested Next roots would otherwise flag a file twice
                    flagged.add(path)
                    facts["incomplete"] += [{"file": path, **i} for i in incomplete(program)]
        return facts


ADAPTER = NextJSAdapter()
