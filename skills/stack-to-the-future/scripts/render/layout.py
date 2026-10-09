"""Shared deterministic layout: the same atlas always gives the same coordinates, whichever renderer draws it.

Plates run left to right. Stages travelled by every variant (or none) sit on the centre lane; a stage that belongs to
exactly one variant goes to that variant's lane (below, above, further below...), so the trunk stays near the top on
phones. Arrows elbow in the gaps between columns: near the source when a branch leaves the trunk, near the target
when it merges back.
"""
import textwrap

from redact import redact, redact_obj

PALETTE = ["#1c7ed6", "#e8590c", "#2b8a3e", "#9c36b5", "#c2255c", "#0c8599"]  # variant colours, in variant order
NEUTRAL = "#495057"
NODE_W, NODE_H, DECISION_W, DECISION_H = 180, 68, 200, 104
COL_W, LANE_H, PAD, TITLE_H = 270, 210, 40, 0
LABEL_LINES, LABEL_LINE_H = 4, 15
LANES = [1, -1, 2, -2, 3, -3, 4, -4]  # first variant just below the trunk; odd counts put the extra lane below
SHAPES = {"start": "pill", "end": "pill", "decision": "diamond", "step": "rect"}
ORDER = {"owner": 0, "helper": 1, "shared_system": 2, "foundation": 3}
RAIL_W, RAIL_H, NOTE_W = 210, 46, 280
FRAME_GAP = 200


def checked(text: str) -> str:
    """Every renderer's last step: refuse to produce output that still looks like it holds a secret."""
    _, hits = redact(text)
    if hits:
        raise ValueError(f"refusing to render: {hits} secret-looking value(s) in the output")
    return text


def guard(atlas: dict) -> None:
    """Every renderer's first step: labels get truncated when drawn, which could cut a secret below what redaction
    recognises, so every string in the full atlas is checked before anything is drawn. (String by string: one JSON
    line would glue a value like "secrets_loading" to the next key and look like an assignment.)"""
    _, hits = redact_obj(atlas)
    if hits:
        raise ValueError(f"refusing to render: {hits} secret-looking value(s) in the atlas")


def wrap(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, width) or [""]


def clip(lines: list[str], n: int) -> list[str]:
    return lines if len(lines) <= n else lines[:n - 1] + [lines[n - 1].rstrip(".,;") + "…"]


def columns(ids: list[str], paths: list[dict]) -> dict[str, int]:
    """Longest-path column per stage. Edges that point backwards in stage order (cycles) don't push columns."""
    succ = {i: [] for i in ids}
    indeg = {i: 0 for i in ids}
    for p in paths:
        if p["from"] in succ and p["to"] in succ and p["from"] != p["to"]:
            succ[p["from"]].append(p["to"])
            indeg[p["to"]] += 1
    order, ready = [], [i for i in ids if indeg[i] == 0]
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in succ[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
    order += [i for i in ids if i not in order]  # stages stuck in a cycle keep their stage order
    rank = {n: k for k, n in enumerate(order)}
    col = {i: 0 for i in ids}
    for n in order:
        for m in succ[n]:
            if rank[m] > rank[n]:
                col[m] = max(col[m], col[n] + 1)
    return col


def bone_labels(stage: dict) -> list[str]:
    files = sorted(stage["files"], key=lambda f: ORDER[f["contribution"]])
    labels = [f.get("label") or f["file"] for f in files]
    labels = [t if len(t) <= 36 else t[:35].rstrip(" ,") + "…" for t in labels]  # full list lives in the stage panel
    if len(labels) > LABEL_LINES:
        labels = labels[:LABEL_LINES - 1] + [f"+{len(labels) - LABEL_LINES + 1} more"]
    return labels


def elbow(sx, sy, tx, ty, near_source, offset):
    if tx > sx:
        x = (sx + 30 + offset) if near_source else (tx - 30 - offset)
        return [[sx, sy], [x, sy], [x, ty], [tx, ty]] if sy != ty else [[sx, sy], [tx, ty]]
    return [[sx, sy], [sx + 20, sy], [sx + 20, sy + 60], [tx - 20, sy + 60], [tx - 20, ty], [tx, ty]]


def plate(workflow: dict, atlas: dict) -> dict:
    stages, paths = workflow["stages"], workflow["paths"]
    ids = [s["id"] for s in stages]
    col = columns(ids, paths)
    vindex = {v["id"]: k for k, v in enumerate(workflow["variants"])}

    marks = {i: set() for i in ids}
    for p in paths:
        for end in (p["from"], p["to"]):
            if end in marks:
                marks[end] |= set(p.get("variants") or ["*"])
    lane, taken = {}, set()
    for sid in sorted(ids, key=lambda i: (col[i], ids.index(i))):
        m = marks[sid]
        want = LANES[vindex[next(iter(m))] % len(LANES)] if len(m) == 1 and "*" not in m else 0
        while (col[sid], want) in taken:
            want = want + 1 if want >= 0 else want - 1
        taken.add((col[sid], want))
        lane[sid] = want
    rows = sorted(set(lane.values()))
    row_cy = {r: PAD + TITLE_H + k * LANE_H + DECISION_H // 2 for k, r in enumerate(rows)}

    nodes = []
    for s in stages:
        w, h = (DECISION_W, DECISION_H) if s["kind"] == "decision" else (NODE_W, NODE_H)
        cx, cy = PAD + col[s["id"]] * COL_W + DECISION_W // 2, row_cy[lane[s["id"]]]
        m = marks[s["id"]]
        nodes.append({
            "id": s["id"], "name": s["name"], "kind": s["kind"], "shape": SHAPES[s["kind"]],
            "status": s.get("status", "complete"), "actor": s.get("actor", ""),
            "x": cx - w // 2, "y": cy - h // 2, "w": w, "h": h, "cx": cx, "cy": cy,
            "lines": wrap(s["name"], 16 if s["kind"] == "decision" else 22),
            "labels": bone_labels(s),
            "variants": sorted(m - {"*"}) if "*" not in m and len(m) == 1 else [],
        })
    by_id = {n["id"]: n for n in nodes}

    edges = []
    for p in paths:
        if p["from"] not in by_id or p["to"] not in by_id:
            continue
        a, b = by_id[p["from"]], by_id[p["to"]]
        variants = p.get("variants") or []
        fan_out = lane[p["from"]] == 0 and lane[p["to"]] != 0
        offset = 7 * min((vindex.get(v, 0) for v in variants), default=0) if fan_out else 0  # merges share one bus
        pts = elbow(a["cx"] + a["w"] // 2, a["cy"], b["cx"] - b["w"] // 2, b["cy"], fan_out, offset)
        if len(pts) > 2:  # elbowed: right-align the label just left of the final bend, in the gap beside it
            label_at, anchor = [pts[-2][0] - 6, pts[-1][1] - 8], "end"
        else:
            label_at, anchor = [(pts[0][0] + pts[1][0]) // 2, pts[0][1] - 8], "middle"
        edges.append({
            "id": p["id"], "from": p["from"], "to": p["to"], "label": p.get("label", ""), "variants": variants,
            "status": p.get("status", "complete"), "points": pts,
            "color": PALETTE[vindex[variants[0]] % len(PALETTE)] if len(variants) == 1 else NEUTRAL,
            "label_at": label_at, "label_anchor": anchor,
        })

    incoming = {}
    for e in edges:
        if len(e["points"]) > 2 and e["points"][-1][0] > e["points"][0][0]:
            incoming.setdefault(e["to"], []).append(e)
    for group in incoming.values():  # 2+ branches rejoining: they share the last bend, so it's a merge
        for e in group:
            e["merge"] = len(group) > 1

    bottom = PAD + TITLE_H + len(rows) * LANE_H
    width = max(PAD * 2 + max(col.values(), default=0) * COL_W + DECISION_W + 70, 900)  # room for the last bone labels

    stage_ids = set(ids)
    rail = []
    for system in atlas.get("shared_systems", []):
        used = [s for s in system["used_by_stages"] if s in stage_ids]
        if used:
            rail.append({"id": system["id"], "name": system["name"], "files": system["files"], "stages": used})
    bottom = flow(rail, RAIL_W, lambda _: RAIL_H, bottom + 10, width)

    notes = []
    for flag in atlas.get("flags", []):
        target = attach(flag["target"], workflow, by_id)
        if target is not False:
            notes.append({"id": flag["id"], "kind": flag["kind"], "target": target, "lines": wrap(flag["message"], 40)})
    bottom = flow(notes, NOTE_W, lambda n: 24 + 16 * len(n["lines"]), bottom + 20, width)

    variants = [{"id": v["id"], "name": v["name"], "condition": v["condition"], "color": PALETTE[k % len(PALETTE)]}
                for k, v in enumerate(workflow["variants"])]
    return {"id": workflow["id"], "title": workflow["name"], "width": width, "height": bottom + PAD,
            "nodes": nodes, "edges": edges, "rail": rail, "notes": notes, "variants": variants}


def attach(target: dict, workflow: dict, by_id: dict):
    """Which node a flag points at on this plate: a node id, None (the plate as a whole), or False (not this plate)."""
    kind, tid = target["type"], target["id"]
    if kind == "stage":
        return tid if tid in by_id else False
    if kind == "path":
        return next((p["to"] for p in workflow["paths"] if p["id"] == tid), False)
    if kind == "workflow":
        return None if tid == workflow["id"] else False
    users = [s for s in workflow["stages"] for f in s["files"] if f["file"] == tid]
    owners = [s for s in users for f in s["files"] if f["file"] == tid and f["contribution"] == "owner"]
    return (owners or users)[0]["id"] if users else False


def flow(items: list[dict], w: int, height, top: int, width: int) -> int:
    """Lay boxes left to right, wrapping at `width`. Sets x/y/w/h on each item; returns the new bottom."""
    x, y, row_h = PAD, top, 0
    for item in items:
        h = height(item)
        if x + w > width - PAD and x > PAD:
            x, y, row_h = PAD, y + row_h + 16, 0
        item.update(x=x, y=y, w=w, h=h)
        x, row_h = x + w + 20, max(row_h, h)
    return y + row_h if items else top


def overview(atlas: dict) -> dict:
    stage_module = {s["id"]: w["module"] for w in atlas["workflows"] for s in w["stages"]}
    cols = min(len(atlas["modules"]), 3) or 1
    boxes = []
    for k, m in enumerate(atlas["modules"]):
        r, c = divmod(k, cols)
        boxes.append({"id": m["id"], "name": m["name"], "summary": clip(wrap(m["summary"], 34), 4),
                      "drawn": m.get("drawn", True), "workflows": len(m["workflows"]),
                      "x": PAD + c * 400, "y": PAD + r * 260, "w": 270, "h": 160})
    by_id = {b["id"]: b for b in boxes}

    pairs = {}
    for link in atlas.get("links", []):
        a, b = stage_module.get(link["from_stage"]), stage_module.get(link["to_stage"])
        if a and b and a != b:
            pairs.setdefault((a, b), []).append(link["label"])
    links = []
    for (a, b), labels in sorted(pairs.items()):
        s, t = by_id[a], by_id[b]
        if t["x"] > s["x"]:
            pts = elbow(s["x"] + s["w"], s["y"] + s["h"] // 2, t["x"], t["y"] + t["h"] // 2, False, 0)
        else:
            pts = [[s["x"] + s["w"] // 2, s["y"] + s["h"]], [s["x"] + s["w"] // 2, s["y"] + s["h"] + 40],
                   [t["x"] + t["w"] // 2, s["y"] + s["h"] + 40], [t["x"] + t["w"] // 2, t["y"]]]
        links.append({"id": f"{a}->{b}", "from": a, "to": b, "lines": wrap("; ".join(labels), 22), "points": pts})

    grid_right = max((b["x"] + b["w"] for b in boxes), default=PAD)
    grid_bottom = max((b["y"] + b["h"] for b in boxes), default=PAD)
    shared = [{"id": s["id"], "name": s["name"], "files": s["files"], "lines": clip(wrap(s["description"], 32), 3),
               "x": grid_right + 120, "y": PAD + k * 100, "w": 250, "h": 84}
              for k, s in enumerate(atlas.get("shared_systems", []))]
    width = max([grid_right + PAD] + [s["x"] + s["w"] + PAD for s in shared])
    groups = [{"group": g["group"], "label": g.get("label") or g["group"].replace("_", " ").capitalize(),
               "files": g["files"][:6] + ([f"+{len(g['files']) - 6} more"] if len(g["files"]) > 6 else [])}
              for g in atlas.get("foundation", [])]
    top = max(grid_bottom, max((s["y"] + s["h"] for s in shared), default=0)) + 90
    bottom = flow(groups, 230, lambda g: 34 + 15 * len(g["files"]), top + 40, width)
    return {"width": width, "height": bottom + PAD, "modules": boxes, "links": links, "shared": shared,
            "foundation": groups, "band": [PAD // 2, top, width - PAD, bottom - top + 20]}


def canvas(atlas: dict) -> list[dict]:
    """Frames for infinite-canvas formats: the overview first, then every workflow plate stacked below it."""
    frames, y = [], 0
    ov = overview(atlas)
    frames.append({"id": "overview", "kind": "overview", "title": f"{atlas['project']['name']}: full body", "x": 0, "y": y, "layout": ov})
    y += ov["height"] + FRAME_GAP
    for wf in atlas["workflows"]:
        p = plate(wf, atlas)
        frames.append({"id": wf["id"], "kind": "plate", "module": wf["module"], "title": wf["name"], "x": 0, "y": y, "layout": p})
        y += p["height"] + FRAME_GAP
    return frames
