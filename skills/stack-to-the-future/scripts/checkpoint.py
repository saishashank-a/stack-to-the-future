"""Human checkpoint: merge drafts with locked corrections, list what a re-scan made stale, and print the outline."""
import copy
import re
from pathlib import Path
from string import Template

import validate
from validate import link_id

OUTLINE = Path(__file__).resolve().parent.parent / "templates" / "outline.md"
LOCKABLE_PARTS = (("stages", "stage"), ("paths", "path"), ("variants", "variant"))


def merge(previous: dict | None, draft: dict, scan: dict) -> dict:
    """The draft, except every item the human locked in the previous atlas wins.

    A locked item whose citations no longer resolve against the scan is still kept, with a stale_override flag
    so the human decides what happens to it.
    """
    out = copy.deepcopy(draft)
    out["flags"] = [f for f in out["flags"] if f["kind"] != "stale_override"]
    if not previous:
        return out
    kept = []

    def keep(items, previous_items, key, kind):
        index = {key(x): i for i, x in enumerate(items)}
        for p in previous_items:
            if p.get("locked"):
                if key(p) in index:
                    items[index[key(p)]] = copy.deepcopy(p)
                else:
                    items.append(copy.deepcopy(p))
                kept.append((kind, key(p)))

    by_id = lambda x: x["id"]  # noqa: E731
    keep(out["modules"], previous["modules"], by_id, "module")
    keep(out["cards"], previous["cards"], lambda c: c["file"], "file")
    keep(out["shared_systems"], previous["shared_systems"], by_id, "shared_system")
    keep(out.setdefault("links", []), previous.get("links", []), link_id, "link")
    drafted = {w["id"]: w for w in out["workflows"]}
    for pw in previous["workflows"]:
        if pw.get("locked"):
            keep(out["workflows"], [pw], by_id, "workflow")
        elif pw["id"] in drafted:
            for part, kind in LOCKABLE_PARTS:
                keep(drafted[pw["id"]][part], pw[part], by_id, kind)
        elif locked := [(kind, x["id"]) for part, kind in LOCKABLE_PARTS for x in pw[part] if x.get("locked")]:
            out["workflows"].append(copy.deepcopy(pw))  # draft dropped a workflow the human corrected: keep it
            kept += locked

    errors = validate.validate(out, scan)
    where = validate.pointers(out)
    for kind, ident in kept:
        pointer = where.get((kind, ident))
        broken = [e for e in errors if e["rule"] in ("evidence", "symbol", "refs")
                  and (e["where"] == pointer or e["where"].startswith(f"{pointer}/"))]
        if pointer and broken:
            cited = next(ev for _, ev in validate.evidence(at(out, pointer)))
            out["flags"].append({
                "id": re.sub(r"[^a-z0-9]+", "-", f"stale {kind} {ident}".lower()).strip("-"),
                "kind": "stale_override",
                "message": f"Kept your correction, but the code it describes has changed: {broken[0]['message']}.",
                "target": {"type": kind, "id": ident},
                "evidence": [cited],
            })
    return out


def at(doc, pointer: str):
    for part in pointer.strip("/").split("/"):
        doc = doc[int(part)] if isinstance(doc, list) else doc[part]
    return doc


def stale(atlas: dict, scan: dict) -> tuple[list[str], list[str]]:
    """(what Claude re-drafts, locked items the human must review) after a re-scan."""
    now = {f["path"]: f for f in scan["files"]}
    before = {f["path"]: f["sha256"] for f in atlas["files"]}
    changed = {p: ("deleted" if p not in now else "changed") for p, h in before.items() if p not in now or now[p]["sha256"] != h}
    redraft, review = [], []

    def check(item, label, locked, extra_files=()):
        cited = {ev["path"] for _, ev in validate.evidence(item)} | set(extra_files)
        if hit := sorted(cited & set(changed)):
            (review if locked else redraft).append(f"{label}: cites {', '.join(f'{p} ({changed[p]})' for p in hit)}")

    for card in atlas["cards"]:
        described = card.get("source_sha256") or before.get(card["file"])
        if card["file"] not in now or now[card["file"]]["sha256"] != described:
            (review if card.get("locked") else redraft).append(
                f"card {card['file']}: file {'deleted' if card['file'] not in now else 'changed'}")
    for w in atlas["workflows"]:
        for part, kind in LOCKABLE_PARTS:
            for x in w[part]:
                check(x, f"{kind} {x['id']}", w.get("locked") or x.get("locked"), [f["file"] for f in x.get("files", [])])
    for link in atlas.get("links", []):
        check(link, f"link {link_id(link)}", link.get("locked"))
    for s in atlas["shared_systems"]:
        check(s, f"shared system {s['id']}", s.get("locked"), s["files"])
    for flag in atlas["flags"]:
        check(flag, f"flag {flag['id']}", False)
    for p, f in sorted(now.items()):
        if p not in before and f["hint"] != "ignored":
            redraft.append(f"new file {p}: " + ("needs a card and a place on a stage" if f["hint"] == "business"
                                                else f"add to foundation group {f.get('group', 'other')}"))
    return redraft, review


def outline(atlas: dict) -> str:
    """The human-checkpoint text: every item with its [id] so corrections can name it."""
    names = {s["id"]: s["name"] for w in atlas["workflows"] for s in w["stages"]}
    lines = []
    for m in atlas["modules"]:
        lines += ["", f"{m['name']}  [module {m['id']}]" + ("  (not yet drawn)" if m.get("drawn") is False else "") + lock(m),
                  f"  {m['summary']}"]
        for w in (w for w in atlas["workflows"] if w["module"] == m["id"]):
            lines += ["", f"  {w['name']}  [workflow {w['id']}]{lock(w)}", f"    {w['summary']}"]
            variant_names = {v["id"]: v["name"] for v in w["variants"]}
            for n, s in enumerate(ordered(w), 1):
                tags = [t for t in (s["kind"].upper() if s["kind"] != "step" else "",
                                    "dotted: not built" if s.get("status") == "incomplete" else "") if t]
                lines.append(f"    {n}. {s['name']}  [{s['id']}]  ({', '.join([s.get('actor', '?'), *tags])}){lock(s)}")
                for p in (p for p in w["paths"] if p["from"] == s["id"]):
                    label = f"({p['label']}) " if p.get("label") else ""
                    via = f"  via {', '.join(variant_names.get(v, v) for v in p['variants'])}" if p.get("variants") else ""
                    dotted = "  (dotted: not built)" if p.get("status") == "incomplete" else ""
                    lines.append(f"         -> {label}{names.get(p['to'], p['to'])}{via}{dotted}  [{p['id']}]{lock(p)}")
            if w["variants"]:
                lines.append("    Branches (all on this one diagram):")
                for v in w["variants"]:
                    route = " > ".join(names.get(s, s) for s in v["route"])
                    lines.append(f"      - {v['name']}  [{v['id']}]: {v['condition']}. {route}. "
                                 f"Rejoins at {names.get(v['route'][-1], v['route'][-1])}.{lock(v)}")
    sections = [
        ("Hand-offs between modules", [f"{names.get(x['from_stage'])} -> {names.get(x['to_stage'])}: {x['label']}  "
                                       f"[link {link_id(x)}]{lock(x)}" for x in atlas.get("links", [])]),
        ("Shared systems", [f"{s['name']}  [{s['id']}]: used by {', '.join(names.get(i, i) for i in s['used_by_stages'])}{lock(s)}"
                            for s in atlas["shared_systems"]]),
        ("Foundation (drawn faded)", [f"{g.get('label') or g['group']}: {', '.join(g['files'])}" for g in atlas["foundation"]]),
        ("Flags (drawn dotted)", [f"{f['kind']}: {f['message']}  [flag {f['id']} on {f['target']['id']}]" for f in atlas["flags"]]),
    ]
    for title, items in sections:
        if items:
            lines += ["", f"{title}:", *(f"  - {i}" for i in items)]
    return Template(OUTLINE.read_text()).substitute(project=atlas["project"]["name"], outline="\n".join(lines).strip("\n"))


def ordered(workflow: dict) -> list[dict]:
    """Stages from the start, each after every stage that leads into it (so a merge point follows all its branches)."""
    stages = {s["id"]: s for s in workflow["stages"]}
    preds = {i: {p["from"] for p in workflow["paths"] if p["to"] == i and p["from"] != i} for i in stages}
    order, ready = [], [s["id"] for s in workflow["stages"] if s["kind"] == "start"]
    while len(order) < len(stages):
        if not ready:  # a loop or an unreachable stage: carry on in written order
            ready = [next(i for i in stages if i not in order)]
        here = ready.pop(0)
        if here in order:
            continue
        order.append(here)
        ready += [p["to"] for p in workflow["paths"] if p["from"] == here and p["to"] in stages
                  and p["to"] not in order and preds[p["to"]] <= set(order)]
    return [stages[i] for i in order]


def lock(item: dict) -> str:
    return "  (yours, locked)" if item.get("locked") else ""
