"""Small tree-sitter helpers shared by the Python adapters."""
from scan import FIRST_STRING, PARSER, descendants

__all__ = ["descendants", "parse", "text", "line", "end", "qualname", "string", "kwarg", "positional", "edge", "files_mentioning"]


def parse(project, path):
    return PARSER.parse(project.source(path)).root_node


def text(n) -> str:
    return n.text.decode("utf-8", "replace")


def line(n) -> int:
    return n.start_point.row + 1


def end(n) -> int:
    return n.end_point.row + 1


def qualname(node) -> str:
    """Qualified name of the def/class around `node`, matching scan.py's symbol names; '<module>' at top level."""
    names, p = [], node.parent
    while p is not None:
        if p.type in ("function_definition", "class_definition"):
            names.append(text(p.child_by_field_name("name")))
        p = p.parent
    return ".".join(reversed(names)) or "<module>"


def string(n) -> str | None:
    """Value of a plain string literal node, else None (f-strings and names are not literals)."""
    if n is None or n.type != "string" or any(c.type == "interpolation" for c in n.children):
        return None
    m = FIRST_STRING.match(text(n))
    return m.group(2) if m else None


def kwarg(call, name):
    args = call.child_by_field_name("arguments")
    for a in args.named_children if args else []:
        if a.type == "keyword_argument" and text(a.child_by_field_name("name")) == name:
            return a.child_by_field_name("value")
    return None


def positional(call) -> list:
    args = call.child_by_field_name("arguments")
    return [a for a in (args.named_children if args else []) if a.type not in ("keyword_argument", "comment")]


def edge(file, caller, ln, target) -> dict:
    return {"file": file, "caller": caller, "line": ln, "target_file": target[0], "target_symbol": target[1]}


def files_mentioning(project, *needles: str) -> list[str]:
    """Python files whose source contains any needle; cheap pre-filter before re-parsing."""
    out = []
    for path in project.facts:
        src = project.source(path)
        if any(n.encode() in src for n in needles):
            out.append(path)
    return out
