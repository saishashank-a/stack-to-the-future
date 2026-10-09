"""SQLAlchemy / SQLModel: event hooks become call edges (model -> listener); enum-typed columns link to status machines."""
import re

from adapters._common import edge, files_mentioning
from scan import enum_classes, models

LISTENS_FOR_RX = re.compile(r"^@\s*(?:[\w.]+\.)?listens_for\(\s*([\w.]+)")
LISTEN_RX = re.compile(r"\bevent\.listen\(\s*([\w.]+)\s*,\s*['\"]\w+['\"]\s*,\s*([\w.]+)")
CAPITALISED = re.compile(r"\b[A-Z]\w*")


class SQLAlchemyAdapter:
    name = "sqlalchemy"

    def applies(self, project) -> bool:
        return project.uses("sqlalchemy") or project.uses("sqlmodel")

    def extract(self, project) -> dict:
        facts = {"calls": [], "status_columns": []}

        def model_class(path, expr):
            # `Order` or `Order.status` (attribute events): the class either way.
            for candidate in (expr, expr.rsplit(".", 1)[0]):
                t = project.resolve(path, candidate)
                if t and project.symbols[t[0]][t[1]]["kind"] == "class":
                    return t
            return None

        def hook(path, model_expr, listener):
            if model := model_class(path, model_expr):
                start = project.symbols[model[0]][model[1]]["start_line"]
                facts["calls"].append(edge(model[0], model[1], start, listener))

        for path, table in project.symbols.items():
            for name, sym in table.items():
                for dec in sym.get("decorators", []):
                    if m := LISTENS_FOR_RX.match(dec):
                        hook(path, m.group(1), (path, name))
        for path in files_mentioning(project, "event.listen("):
            for m in LISTEN_RX.finditer(project.source(path).decode("utf-8", "replace")):
                if listener := project.resolve(path, m.group(2)):
                    hook(path, m.group(1), listener)

        enums = enum_classes(project)
        for model in (m for m in models(project) if m["kind"] == "orm"):  # stored columns, not request/response shapes
            lines = project.source(model["file"]).decode("utf-8", "replace").splitlines()
            for field in model["fields"]:
                sym = project.symbols[model["file"]][f"{model['name']}.{field}"]
                body = "\n".join(lines[sym["start_line"] - 1:sym["end_line"]])
                for word in sorted(set(CAPITALISED.findall(body))):
                    target = project.resolve(model["file"], word)
                    if target in enums:
                        facts["status_columns"].append({"file": model["file"], "model": model["name"], "field": field,
                                                        "line": sym["start_line"], "enum_file": target[0], "enum": target[1]})
                        break
        return facts


ADAPTER = SQLAlchemyAdapter()
