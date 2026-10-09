"""Celery: tasks dispatched by name (send_task) become call edges; beat schedules become scheduled entry points."""
from adapters._common import descendants, edge, end, files_mentioning, kwarg, line, parse, positional, qualname, string, text

SCHEDULE_NAMES = ("beat_schedule", "CELERYBEAT_SCHEDULE", "CELERY_BEAT_SCHEDULE")


def schedule_dict(n):
    """The dict literal in `x.beat_schedule = {...}` or `conf.update(beat_schedule={...})`, else None."""
    if n.type == "assignment" and text(n.child_by_field_name("left")).rsplit(".", 1)[-1] in SCHEDULE_NAMES:
        value = n.child_by_field_name("right")
    elif n.type == "keyword_argument" and text(n.child_by_field_name("name")) in SCHEDULE_NAMES:
        value = n.child_by_field_name("value")
    else:
        return None
    return value if value is not None and value.type == "dictionary" else None


class CeleryAdapter:
    name = "celery"

    def applies(self, project) -> bool:
        return project.uses("celery")

    def extract(self, project) -> dict:
        # Registered task name -> (file, symbol): explicit name=..., else Celery's default "module.function".
        tasks = {}
        for ep in project.entry_points:
            if ep["kind"] == "background_job":
                tasks.setdefault(ep["label"], (ep["file"], ep["symbol"]))
                tasks.setdefault(f"{ep['file'][:-3].replace('/', '.')}.{ep['symbol']}", (ep["file"], ep["symbol"]))

        facts = {"calls": [], "entry_points": []}
        for path in files_mentioning(project, "send_task", *SCHEDULE_NAMES):
            for n in descendants(parse(project, path)):
                if n.type == "call" and text(n.child_by_field_name("function")).endswith("send_task"):
                    args = positional(n)
                    target = tasks.get(string(args[0]) if args else string(kwarg(n, "name")))
                    if target:
                        facts["calls"].append(edge(path, qualname(n), line(n), target))
                elif (schedule := schedule_dict(n)) is not None:
                    facts["entry_points"] += self._beat(path, schedule, tasks, facts["calls"])
        return facts

    def _beat(self, path, schedule, tasks, calls) -> list:
        found = []
        for pair in (p for p in schedule.named_children if p.type == "pair"):
            spec = pair.child_by_field_name("value")
            if spec is None or spec.type != "dictionary":
                continue
            fields = {string(p.child_by_field_name("key")): p.child_by_field_name("value")
                      for p in spec.named_children if p.type == "pair"}
            name = string(fields.get("task"))
            if not name:
                continue
            when = text(fields["schedule"]) if fields.get("schedule") is not None else "scheduled"
            caller = qualname(pair)
            found.append({"kind": "scheduled_job", "label": f"{name} ({when})", "file": path, "symbol": caller,
                          "start_line": line(pair), "end_line": end(pair), "id": f"{path}::{caller}@{line(pair)}"})
            if name in tasks:
                calls.append(edge(path, caller, line(pair), tasks[name]))
        return found


ADAPTER = CeleryAdapter()
