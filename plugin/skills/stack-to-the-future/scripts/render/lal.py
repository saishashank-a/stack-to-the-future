"""Atlas -> .lal scene for Sir Lines-a-Lot (spec: references/lal-format.md). Depends only on the shared layout."""
import json

from . import layout as L

FADED = "#adb5bd"
NOTE, NOTE_FILL, SOFT = "#e0a800", "#fff4d6", "#f1f3f5"


def render(atlas: dict) -> str:
    L.guard(atlas)
    nodes, connectors, callouts, legends, frames = [], [], [], [], []
    first_plate = {}
    canvas = L.canvas(atlas)
    for fr in canvas:
        if fr["kind"] == "plate":
            first_plate.setdefault(fr["module"], fr["id"])

    def node(nid, frame, layer, shape, x, y, w, h, label, source, sublabels=(), caption=None, stroke="solid", color=L.NEUTRAL, fill=None, link=None):
        n = {"id": nid, "frame": frame, "layer": layer, "shape": shape, "x": x, "y": y, "width": w, "height": h,
             "label": label, "sublabels": list(sublabels), "style": {"stroke": stroke, "color": color, "fill": fill},
             "link": link, "source": source}
        if caption:
            n["caption"] = caption
        nodes.append(n)

    def connector(cid, frame, layer, a, b, points, color, source, label="", stroke="solid", group=None, width=2, arrow="end"):
        connectors.append({"id": cid, "frame": frame, "layer": layer, "from": a, "to": b, "label": label, "points": points,
                           "style": {"stroke": stroke, "color": color, "width": width, "arrow": arrow}, "group": group, "source": source})

    for fr in canvas:
        f, ox, oy, lay = fr["id"], fr["x"], fr["y"], fr["layout"]
        frames.append({"id": f, "kind": fr["kind"], "title": fr["title"], "x": ox, "y": oy, "width": lay["width"], "height": lay["height"]})
        if fr["kind"] == "overview":
            bx, by, bw, bh = lay["band"]
            if lay["foundation"]:
                node("foundation:band", f, "foundation", "band", ox + bx, oy + by, bw, bh, "Foundation", {"kind": "band", "id": "foundation"},
                     stroke="dotted", color=FADED, fill=SOFT)
            for g in lay["foundation"]:
                node(f"foundation:{g['group']}", f, "foundation", "note", ox + g["x"], oy + g["y"], g["w"], g["h"], g["label"],
                     {"kind": "foundation_group", "id": g["group"]}, sublabels=g["files"], color=FADED)
            for m in lay["modules"]:
                node(f"module:{m['id']}", f, "business", "rect", ox + m["x"], oy + m["y"], m["w"], m["h"],
                     m["name"] + "\n" + "\n".join(m["summary"]), {"kind": "module", "id": m["id"]},
                     stroke="solid" if m["drawn"] else "dashed", color="#1c7ed6" if m["drawn"] else FADED, link=first_plate.get(m["id"]))
            for s in lay["shared"]:
                node(f"shared:{s['id']}", f, "business", "note", ox + s["x"], oy + s["y"], s["w"], s["h"],
                     s["name"] + "\n" + "\n".join(s["lines"]), {"kind": "shared_system", "id": s["id"]}, sublabels=s["files"], fill=SOFT)
            for link in lay["links"]:
                connector(f"link:{link['id']}", f, "business", f"module:{link['from']}", f"module:{link['to']}",
                          shift(link["points"], ox, oy), L.NEUTRAL, {"kind": "link", "id": link["id"]}, label=" ".join(link["lines"]))
            continue

        for n in lay["nodes"]:
            color = next((v["color"] for v in lay["variants"] if v["id"] in n["variants"]), L.NEUTRAL)
            node(f"stage:{n['id']}", f, "business", n["shape"], ox + n["x"], oy + n["y"], n["w"], n["h"], "\n".join(n["lines"]),
                 {"kind": "stage", "id": n["id"]}, sublabels=n["labels"], caption=n["actor"] or None,
                 stroke="dashed" if n["status"] == "incomplete" else "solid", color=color)
        for e in lay["edges"]:
            connector(f"path:{e['id']}", f, "business", f"stage:{e['from']}", f"stage:{e['to']}", shift(e["points"], ox, oy),
                      e["color"], {"kind": "path", "id": e["id"]}, label=e["label"],
                      stroke="dashed" if e["status"] == "incomplete" else "solid",
                      group=e["variants"][0] if len(e["variants"]) == 1 else None)
        for r in lay["rail"]:
            rid = f"rail:{f}:{r['id']}"
            node(rid, f, "business", "note", ox + r["x"], oy + r["y"], r["w"], r["h"], r["name"],
                 {"kind": "shared_system", "id": r["id"]}, sublabels=r["files"], fill=SOFT)
        for k, note in enumerate(lay["notes"], 1):
            callouts.append({"id": f"flag:{f}:{note['id']}", "frame": f, "layer": "annotations",
                             "target": f"stage:{note['target']}" if note["target"] else None, "kind": note["kind"],
                             "text": f"{k}. " + " ".join(note["lines"]), "x": ox + note["x"], "y": oy + note["y"],
                             "width": note["w"], "height": note["h"]})
        if lay["variants"]:
            legends.append({"frame": f, "entries": [{"id": v["id"], "label": v["name"], "detail": v["condition"], "color": v["color"]}
                                                    for v in lay["variants"]]})

    doc = {"lal_version": "0.1", "title": atlas["project"]["name"], "generator": "stack-to-the-future",
           "layers": [{"id": "foundation", "name": "Foundation", "opacity": 0.4},
                      {"id": "business", "name": "Business", "opacity": 1},
                      {"id": "annotations", "name": "Notes", "opacity": 1}],
           "frames": frames, "nodes": nodes, "connectors": connectors, "callouts": callouts, "legends": legends}
    return L.checked(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")


def shift(points, ox, oy):
    return [[x + ox, y + oy] for x, y in points]
