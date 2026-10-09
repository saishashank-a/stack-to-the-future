"""Excalidraw scene: one frame for the full-body overview, one frame per workflow plate. Hand-drawn by default."""
import hashlib
import json

from . import layout as L

FONT_HAND, FONT_MONO = 1, 3


def seed(key: str) -> int:
    return int(hashlib.sha1(key.encode()).hexdigest()[:8], 16) % 2_000_000_000


def base(eid: str, kind: str, x, y, w, h, frame, **extra) -> dict:
    el = {"id": eid, "type": kind, "x": x, "y": y, "width": w, "height": h, "angle": 0,
          "strokeColor": "#1e1e1e", "backgroundColor": "transparent", "fillStyle": "solid", "strokeWidth": 2,
          "strokeStyle": "solid", "roughness": 1, "opacity": 100, "groupIds": [], "frameId": frame,
          "roundness": None, "seed": seed(eid), "version": 1, "versionNonce": seed(eid + "#"), "isDeleted": False,
          "boundElements": [], "updated": 1, "link": None, "locked": False}
    el.update(extra)
    return el


def text_el(eid, lines, x, y, w, frame, size=16, family=FONT_HAND, container=None, align="center", color="#1e1e1e", opacity=100):
    content = "\n".join(lines)
    h = round(len(lines) * size * 1.25)
    return base(eid, "text", x, y, w, h, frame, strokeColor=color, opacity=opacity, text=content, originalText=content,
                fontSize=size, fontFamily=family, textAlign=align, verticalAlign="middle" if container else "top",
                containerId=container, lineHeight=1.25, autoResize=True)


class Scene:
    def __init__(self):
        self.elements = []
        self.ids = {}

    def add(self, el):
        self.elements.append(el)
        self.ids[el["id"]] = el
        return el

    def boxed(self, eid, kind, x, y, w, h, frame, lines, size=16, dashed=False, color="#1e1e1e", fill="transparent", opacity=100, rounded=True):
        shape = self.add(base(eid, kind, x, y, w, h, frame, strokeColor=color, backgroundColor=fill, opacity=opacity,
                              strokeStyle="dashed" if dashed else "solid", roundness={"type": 3} if rounded and kind == "rectangle" else None))
        label = self.add(text_el(eid + ":text", lines, x + 8, y + h / 2 - len(lines) * size * 0.625, w - 16, frame,
                                 size=size, container=eid, opacity=opacity))
        shape["boundElements"].append({"type": "text", "id": label["id"]})
        return shape

    def arrow(self, eid, points, frame, start, end, color, dashed=False, label=None, opacity=100, width=2):
        x0, y0 = points[0]
        rel = [[px - x0, py - y0] for px, py in points]
        xs, ys = [p[0] for p in rel], [p[1] for p in rel]
        el = self.add(base(eid, "arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys), frame, strokeColor=color,
                           strokeStyle="dashed" if dashed else "solid", opacity=opacity, strokeWidth=width,
                           roundness={"type": 2}, points=rel, lastCommittedPoint=None, startArrowhead=None, endArrowhead="arrow",
                           startBinding={"elementId": start, "focus": 0, "gap": 4} if start else None,
                           endBinding={"elementId": end, "focus": 0, "gap": 4} if end else None, elbowed=False))
        for target in (start, end):
            if target:
                self.ids[target]["boundElements"].append({"type": "arrow", "id": eid})
        if label:
            mx, my = points[-2] if len(points) > 2 else points[0]
            t = self.add(text_el(eid + ":label", [label], mx - 60, my - 22, 120, frame, size=14, container=eid))
            el["boundElements"].append({"type": "text", "id": t["id"]})
        return el

    def frame(self, eid, name, x, y, w, h):
        # frames go after their children so the children stay inside on import
        self.add(base(eid, "frame", x, y, w, h, None, name=name, roughness=0, strokeWidth=1))


def render(atlas: dict) -> str:
    L.guard(atlas)
    s = Scene()
    for fr in L.canvas(atlas):
        fid, ox, oy, lay = f"frame:{fr['id']}", fr["x"], fr["y"], fr["layout"]
        if fr["kind"] == "overview":
            overview(s, lay, fid, ox, oy)
        else:
            plate(s, lay, fid, ox, oy)
        s.frame(fid, fr["title"], ox, oy, lay["width"], lay["height"])
    doc = {"type": "excalidraw", "version": 2, "source": "stack-to-the-future",
           "elements": s.elements, "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}}
    return L.checked(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")


def plate(s: Scene, p: dict, fid: str, ox: int, oy: int) -> None:
    for n in p["nodes"]:
        kind = {"diamond": "diamond", "pill": "ellipse"}.get(n["shape"], "rectangle")
        color = L.PALETTE[[v["id"] for v in p["variants"]].index(n["variants"][0]) % len(L.PALETTE)] if n["variants"] else L.NEUTRAL
        s.boxed(f"stage:{n['id']}", kind, ox + n["x"], oy + n["y"], n["w"], n["h"], fid, n["lines"],
                dashed=n["status"] == "incomplete", color=color)
        if n["actor"]:
            s.add(text_el(f"stage:{n['id']}:actor", [n["actor"].upper()], ox + n["cx"] - 80, oy + n["y"] - 22, 160, fid, size=12, color="#868e96"))
        s.add(text_el(f"stage:{n['id']}:bones", n["labels"], ox + n["cx"] - 140, oy + n["y"] + n["h"] + 8, 280, fid,
                      size=12, family=FONT_MONO, color="#868e96"))
    for e in p["edges"]:
        s.arrow(f"path:{e['id']}", [[ox + x, oy + y] for x, y in e["points"]], fid, f"stage:{e['from']}", f"stage:{e['to']}",
                e["color"], dashed=e["status"] == "incomplete", label=e["label"] or None)
    for r in p["rail"]:
        s.boxed(f"rail:{p['id']}:{r['id']}", "rectangle", ox + r["x"], oy + r["y"], r["w"], r["h"], fid, [r["name"]],
                size=15, fill="#f1f3f5")
    for k, note in enumerate(p["notes"], 1):
        nid = f"note:{p['id']}:{note['id']}"
        s.boxed(nid, "rectangle", ox + note["x"], oy + note["y"], note["w"], note["h"], fid,
                [f"{k}. {note['kind'].replace('_', ' ').upper()}", *note["lines"]], size=13, dashed=True, color="#e0a800", fill="#fff4d6")
        if note["target"]:
            t = s.ids[f"stage:{note['target']}"]
            s.arrow(f"{nid}:tether", [[ox + note["x"] + 20, oy + note["y"]], [t["x"] + t["width"] / 2, t["y"] + t["height"]]],
                    fid, nid, t["id"], "#e0a800", dashed=True, opacity=60, width=1)


def overview(s: Scene, o: dict, fid: str, ox: int, oy: int) -> None:
    bx, by, bw, bh = o["band"]
    if o["foundation"]:
        s.add(base(f"{fid}:band", "rectangle", ox + bx, oy + by, bw, bh, fid, strokeStyle="dotted", opacity=40,
                   backgroundColor="#f1f3f5", roundness={"type": 3}))
        s.add(text_el(f"{fid}:band:title", ["FOUNDATION"], ox + bx + 20, oy + by + 10, 300, fid, size=14, align="left", opacity=50))
        for g in o["foundation"]:
            s.boxed(f"foundation:{g['group']}", "rectangle", ox + g["x"], oy + g["y"], g["w"], g["h"], fid,
                    [g["label"], *g["files"]], size=12, opacity=40)
    for m in o["modules"]:
        s.boxed(f"module:{m['id']}", "rectangle", ox + m["x"], oy + m["y"], m["w"], m["h"], fid,
                [m["name"], "", *m["summary"]], size=15, dashed=not m["drawn"], color="#1c7ed6" if m["drawn"] else "#adb5bd")
    for link in o["links"]:
        s.arrow(f"link:{link['id']}", [[ox + x, oy + y] for x, y in link["points"]], fid,
                f"module:{link['from']}", f"module:{link['to']}", L.NEUTRAL, label=" ".join(link["lines"]))
    for sh in o["shared"]:
        s.boxed(f"shared:{sh['id']}", "rectangle", ox + sh["x"], oy + sh["y"], sh["w"], sh["h"], fid,
                [sh["name"], *sh["lines"]], size=13, fill="#f1f3f5")
