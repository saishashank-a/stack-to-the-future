"""One self-contained HTML file: inline CSS, SVG and a little JS. No network requests; opens from file://."""
import html

from . import layout as L

CONTRIBUTION = {"owner": "Owner", "helper": "Helper", "shared_system": "Shared system", "foundation": "Foundation"}
DARK = ["#74c0fc", "#ffa94d", "#8ce99a", "#e599f7", "#faa2c1", "#66d9e8"]


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def text(lines, cx, y, cls, line_h=17):
    spans = "".join(f'<tspan x="{cx}" dy="{0 if k == 0 else line_h}">{esc(t)}</tspan>' for k, t in enumerate(lines))
    return f'<text class="{cls}" x="{cx}" y="{y}" text-anchor="middle">{spans}</text>'


def path_d(points) -> str:
    return "M" + " L".join(f"{x} {y}" for x, y in points)


def tone(variants, vindex) -> str:
    return f"v{vindex[variants[0]] % len(L.PALETTE)}" if len(variants) == 1 and variants[0] in vindex else "n"


def shape(n) -> str:
    x, y, w, h = n["x"], n["y"], n["w"], n["h"]
    if n["shape"] == "diamond":
        return f'<polygon class="shape" points="{x + w // 2},{y} {x + w},{y + h // 2} {x + w // 2},{y + h} {x},{y + h // 2}"/>'
    return f'<rect class="shape" x="{x}" y="{y}" width="{w}" height="{h}" rx="{h // 2 if n["shape"] == "pill" else 10}"/>'


def plate_svg(p: dict) -> str:
    vindex = {v["id"]: k for k, v in enumerate(p["variants"])}
    out = [f'<svg class="plate" width="{p["width"]}" height="{p["height"]}" viewBox="0 0 {p["width"]} {p["height"]}" role="img" aria-label="{esc(p["title"])}">']
    merged = {}
    for e in p["edges"]:
        t = tone(e["variants"], vindex)
        cls = "edge" + (" incomplete" if e["status"] == "incomplete" else "")
        pts, arrow = e["points"], f' marker-end="url(#arrow-{t})"'
        if e.get("merge"):  # coloured line stops at the shared bend; one neutral arrow enters the stage
            merged[e["to"]] = pts[-2:]
            pts, arrow = pts[:-1], ""
        out.append(f'<g class="{cls}" data-v="{esc(" ".join(e["variants"]) or "*")}" style="--c:var(--{t})">'
                   f'<path d="{path_d(pts)}"{arrow}/>')
        if e["label"]:
            out.append(f'<text class="edge-label" x="{e["label_at"][0]}" y="{e["label_at"][1]}" text-anchor="{e["label_anchor"]}">{esc(e["label"])}</text>')
        out.append("</g>")
    for stub in merged.values():
        out.append(f'<g class="edge merge" data-v="*" style="--c:var(--n)"><path d="{path_d(stub)}" marker-end="url(#arrow-n)"/></g>')
    for n in p["nodes"]:
        t = tone(n["variants"], vindex)
        cls = f'node k-{n["kind"]}' + (" incomplete" if n["status"] == "incomplete" else "")
        top = n["cy"] - (len(n["lines"]) - 1) * 8 + 5
        out.append(f'<g class="{cls}" data-stage="{esc(n["id"])}" data-v="{esc(" ".join(n["variants"]) or "*")}" '
                   f'style="--c:var(--{t})" tabindex="0" role="button" aria-label="{esc(n["name"])}">'
                   f'<title>{esc(n["actor"])}{" · not built yet" if n["status"] == "incomplete" else ""}</title>'
                   + shape(n) + text(n["lines"], n["cx"], top, "name")
                   + (text([n["actor"]], n["cx"], n["y"] - 8, "actor") if n["actor"] else "")
                   + text(n["labels"], n["cx"], n["y"] + n["h"] + 18, "bone", 15) + "</g>")
    for r in p["rail"]:
        out.append(f'<a class="rail" href="#f/{esc(r["files"][0])}" data-stages="{esc(" ".join(r["stages"]))}">'
                   f'<rect x="{r["x"]}" y="{r["y"]}" width="{r["w"]}" height="{r["h"]}" rx="23"/>'
                   + text(["⚙ " + r["name"]], r["x"] + r["w"] // 2, r["y"] + 28, "rail-name") + "</a>")
    by_id = {n["id"]: n for n in p["nodes"]}
    for k, note in enumerate(p["notes"], 1):
        x, y, w, h = note["x"], note["y"], note["w"], note["h"]
        target = by_id.get(note["target"])
        if target:  # numbered badge on the stage instead of a tether line across the plate
            bx, by_ = (target["cx"] + target["w"] // 4, target["y"] + 10) if target["shape"] == "diamond" else (target["x"] + target["w"] - 4, target["y"] + 4)
            out.append(f'<g class="badge"><circle cx="{bx}" cy="{by_}" r="11"/><text x="{bx}" y="{by_ + 4}" text-anchor="middle">{k}</text></g>')
        out.append(f'<g class="note"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>'
                   f'<text class="note-kind" x="{x + 12}" y="{y + 18}">{k}. {esc(note["kind"].replace("_", " ").upper())}</text>'
                   + "".join(f'<text class="note-text" x="{x + 12}" y="{y + 36 + 16 * k}">{esc(t)}</text>' for k, t in enumerate(note["lines"]))
                   + "</g>")
    return "".join(out) + "</svg>"


def overview_svg(o: dict) -> str:
    out = [f'<svg class="overview" viewBox="0 0 {o["width"]} {o["height"]}" role="img" aria-label="Full-body overview">']
    bx, by, bw, bh = o["band"]
    if o["foundation"]:
        out.append(f'<g class="foundation"><rect class="band" x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="14"/>'
                   f'<text class="band-title" x="{bx + 20}" y="{by + 26}">FOUNDATION · plumbing under everything</text>')
        for g in o["foundation"]:
            out.append(f'<rect class="group" x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" rx="8"/>'
                       f'<text class="group-name" x="{g["x"] + 12}" y="{g["y"] + 20}">{esc(g["label"])}</text>'
                       + "".join(f'<text class="bone" x="{g["x"] + 12}" y="{g["y"] + 38 + 15 * k}">{esc(f)}</text>' for k, f in enumerate(g["files"])))
        out.append("</g>")
    for link in o["links"]:
        (x1, y1), (x2, y2) = link["points"][-2], link["points"][-1]
        out.append(f'<g class="edge" style="--c:var(--n)"><path d="{path_d(link["points"])}" marker-end="url(#arrow-n)"/>'
                   + text(link["lines"], (x1 + x2) // 2, min(y1, y2) - 12 - 15 * (len(link["lines"]) - 1), "edge-label", 15) + "</g>")
    for m in o["modules"]:
        cx = m["x"] + m["w"] // 2
        out.append(f'<a class="module{"" if m["drawn"] else " undrawn"}" href="#m/{esc(m["id"])}">'
                   f'<rect x="{m["x"]}" y="{m["y"]}" width="{m["w"]}" height="{m["h"]}" rx="14"/>'
                   + text([m["name"]], cx, m["y"] + 32, "module-name")
                   + text(m["summary"], cx, m["y"] + 58, "module-summary", 16)
                   + text([f'{m["workflows"]} workflow{"s" if m["workflows"] != 1 else ""}' if m["drawn"] else "not yet drawn"],
                          cx, m["y"] + m["h"] - 14, "module-meta") + "</a>")
    for s in o["shared"]:
        out.append(f'<a class="rail" href="#f/{esc(s["files"][0])}"><rect x="{s["x"]}" y="{s["y"]}" width="{s["w"]}" height="{s["h"]}" rx="12"/>'
                   + text(["⚙ " + s["name"]], s["x"] + s["w"] // 2, s["y"] + 24, "rail-name")
                   + text(s["lines"], s["x"] + s["w"] // 2, s["y"] + 44, "module-summary", 15) + "</a>")
    return "".join(out) + "</svg>"


def card_html(card: dict, stage_names: dict) -> str:
    def handoffs(items, arrow):
        rows = []
        for i in items:
            where = f' <span class="muted">{arrow} {esc(i["from_or_to"])}</span>' if i.get("from_or_to") else ""
            rows.append(f"<li>{esc(i['what'])}{where}</li>")
        return "".join(rows) or '<li class="muted">nothing</li>'
    stages = "".join(f'<li><a href="#s/{esc(s)}">{esc(stage_names.get(s, s))}</a></li>' for s in card["stages"])
    evidence = "".join(f'<li>{esc(e["path"])}:{e["start_line"]}–{e["end_line"]}</li>' for e in card["evidence"])
    return (f'<article class="card" data-card="{esc(card["file"])}">'
            f'<p class="eyebrow c-{card["contribution"]}">{CONTRIBUTION[card["contribution"]]}</p>'
            f'<h3 class="mono">{esc(card["file"])}</h3><p class="role">{esc(card["role"])}</p><dl>'
            f'<dt>Serves</dt><dd><ul>{stages or "<li class=muted>no stage</li>"}</ul></dd>'
            f'<dt>Receives</dt><dd><ul>{handoffs(card["receives"], "from")}</ul></dd>'
            f'<dt>Hands off</dt><dd><ul>{handoffs(card["hands_off"], "to")}</ul></dd>'
            f'<dt>If this file is gone</dt><dd class="breaks">{esc(card["if_removed"])}</dd>'
            f'<dt>Evidence</dt><dd><ul class="mono">{evidence}</ul></dd></dl></article>')


def stage_html(stage: dict, module: str) -> str:
    files = "".join(f'<li data-file="{esc(f["file"])}">{esc(f.get("label") or f["file"])} <span class="muted">· {CONTRIBUTION[f["contribution"]]}</span></li>'
                    for f in sorted(stage["files"], key=lambda f: L.ORDER[f["contribution"]]))
    status = '<p class="pill-tag">Not built yet</p>' if stage.get("status") == "incomplete" else ""
    return (f'<article class="stage-head" data-stage="{esc(stage["id"])}" data-module="{esc(module)}">'
            f'<p class="eyebrow">{esc(stage.get("actor", ""))} · {esc(stage["kind"])}</p><h2>{esc(stage["name"])}</h2>{status}'
            f'<p>{esc(stage["description"])}</p><h4>Files on this stage</h4><ul class="files">{files}</ul></article>')


def render(atlas: dict) -> str:
    L.guard(atlas)
    stage_names = {s["id"]: s["name"] for w in atlas["workflows"] for s in w["stages"]}
    workflows = {w["id"]: w for w in atlas["workflows"]}
    cards = {c["file"]: c for c in atlas["cards"]}
    store = [card_html(c, stage_names) for c in atlas["cards"]]
    store += [stage_html(s, w["module"]) for w in atlas["workflows"] for s in w["stages"]]

    views = [f'<section data-view="overview"><p class="lede">{esc(atlas["project"].get("summary", ""))}</p>'
             '<p class="hint">Each box is a part of the business. Click one to open its diagrams; click any step there to see the files behind it.</p>'
             f'<div class="scroll wide">{overview_svg(L.overview(atlas))}</div>{LEGEND}<ul class="module-list">'
             + "".join(f'<li><a href="#m/{esc(m["id"])}">{esc(m["name"])}</a> <span class="muted">{esc(m["summary"])}</span></li>' for m in atlas["modules"])
             + '</ul></section>']
    for m in atlas["modules"]:
        eps = "".join(f'<li><span class="mono">{esc(e["label"])}</span> <span class="muted">{esc(e["kind"].replace("_", " "))}</span></li>' for e in m.get("entry_points", []))
        parts = [f'<section data-view="m/{esc(m["id"])}" hidden><a class="back" href="#overview">← Full body</a>'
                 f'<h2>{esc(m["name"])}</h2><p class="lede">{esc(m["summary"])}</p>']
        if not m.get("drawn", True):
            parts.append('<p class="pill-tag">Not yet drawn. Ask for this module to be drafted.</p>')
        for wid in m["workflows"]:
            if wid not in workflows:
                continue
            p = L.plate(workflows[wid], atlas)
            buttons = "".join(f'<button type="button" data-variant="{esc(v["id"])}" style="--c:var(--v{k % len(L.PALETTE)})" title="{esc(v["condition"])}">'
                              f'<i></i>{esc(v["name"])}</button>' for k, v in enumerate(p["variants"]))
            toolbar = (f'<div class="toolbar" role="group" aria-label="Highlight a route"><button type="button" data-variant="" aria-pressed="true">All routes</button>{buttons}</div>'
                       if p["variants"] else "")
            parts.append(f'<article class="workflow"><h3>{esc(p["title"])}</h3><p>{esc(workflows[wid]["summary"])}</p>'
                         f'{toolbar}<div class="scroll">{plate_svg(p)}</div></article>')
        files = "".join(f'<li><a class="mono" href="#f/{esc(f)}">{esc(f)}</a> <span class="muted">{esc(cards[f]["role"])}</span></li>'
                        for f in m["files"] if f in cards)
        parts.append(f'<details><summary>Ways in ({len(m.get("entry_points", []))})</summary><ul>{eps}</ul></details>'
                     f'<details open><summary>Files in this part ({len([f for f in m["files"] if f in cards])})</summary><ul class="index">{files}</ul></details></section>')
        views.append("".join(parts))

    name = esc(atlas["project"]["name"])
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{name} atlas</title><link rel="icon" href="data:,"><style>{CSS}</style></head><body>'
            f'<header><p class="eyebrow">Stack to the Future · anatomy atlas</p><h1><a href="#overview">{name}</a></h1></header>'
            f'{MARKERS}<main>{"".join(views)}</main>'
            f'<dialog id="panel"><form method="dialog"><button class="close" aria-label="Close">×</button></form><div id="panel-body"></div></dialog>'
            f'<div id="store" hidden>{"".join(store)}</div><script>{JS}</script></body></html>')
    return L.checked(page)


MARKERS = ('<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>'
           + "".join(f'<marker id="arrow-{t}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                     f'<path d="M0 0 L10 5 L0 10 z" style="fill:var(--{t})"/></marker>' for t in ["n"] + [f"v{k}" for k in range(len(L.PALETTE))])
           + "</defs></svg>")

LEGEND = ('<ul class="legend"><li><b class="sw pill"></b>Start or finish</li><li><b class="sw rect"></b>A step</li>'
          '<li><b class="sw diamond"></b>A decision</li><li><b class="sw dotted"></b>Not built yet</li>'
          '<li><b class="sw faded"></b>Foundation (plumbing)</li><li><span class="mono">file.py: name</span> the code behind a step</li></ul>')

_vars = "".join(f"--v{k}:{c};" for k, c in enumerate(L.PALETTE))
_dark = "".join(f"--v{k}:{c};" for k, c in enumerate(DARK))
CSS = f""":root{{color-scheme:light dark;--bg:#fbfaf7;--fg:#1f2328;--muted:#5f6670;--card:#ffffff;--line:#d8d4cc;--node:#ffffff;
--faint:#efece6;--n:{L.NEUTRAL};--accent:#1c7ed6;--note:#fff4d6;--note-line:#e0a800;{_vars}}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e8e6e3;--muted:#a3a9b1;--card:#1f2228;--line:#3a3f47;--node:#23272e;
--faint:#1d2025;--n:#adb5bd;--accent:#74c0fc;--note:#3a3220;--note-line:#e0a800;{_dark}}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
header,main{{max-width:1180px;margin:0 auto;padding:0 16px}}header{{padding-top:24px}}h1{{margin:0 0 8px;font-size:1.8rem}}h1 a{{color:inherit;text-decoration:none}}
h2{{margin:.2em 0}}a{{color:var(--accent)}}.eyebrow{{margin:0;font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
.lede{{font-size:1.05rem;max-width:70ch}}.hint,.muted{{color:var(--muted)}}.mono,.bone{{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}}
.scroll{{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--card);margin:12px 0}}.scroll svg{{display:block}}
.wide svg{{width:100%;min-width:760px;height:auto}}.workflow{{margin:28px 0}}.back{{display:inline-block;margin:12px 0}}
svg text{{fill:var(--fg)}}.shape{{fill:var(--node);stroke:var(--c);stroke-width:2.2}}
.node{{cursor:pointer}}.node:hover .shape,.node:focus .shape{{stroke-width:3.5;fill:var(--faint)}}.node:focus{{outline:none}}
.node .name{{font-size:14px;font-weight:600}}.node .actor{{font-size:11px;fill:var(--muted);letter-spacing:.06em;text-transform:uppercase}}
.bone{{font-size:11.5px;fill:var(--muted)}}.incomplete .shape,.incomplete path{{stroke-dasharray:7 6}}.incomplete .name{{fill:var(--muted)}}
.edge path{{fill:none;stroke:var(--c);stroke-width:2.2;stroke-linejoin:round}}.edge-label{{font-size:12.5px;font-style:italic;paint-order:stroke;stroke:var(--card);stroke-width:5px}}
.dim{{opacity:.15}}.rail rect{{fill:var(--faint);stroke:var(--line);stroke-width:1.5}}.rail-name{{font-size:13.5px;font-weight:600}}
.note rect{{fill:var(--note);stroke:var(--note-line);stroke-dasharray:4 3}}.note-kind{{font-size:10.5px;font-weight:700;letter-spacing:.08em;fill:var(--note-line)}}
.note-text{{font-size:12.5px}}.badge circle{{fill:var(--note-line)}}.badge text{{font-size:12px;font-weight:700;fill:#1f2328}}
.module rect{{fill:var(--node);stroke:var(--accent);stroke-width:2.5}}.module:hover rect{{fill:var(--faint)}}
.module-name{{font-size:19px;font-weight:700}}.module-summary{{font-size:12.5px;fill:var(--muted)}}.module-meta{{font-size:12px;font-weight:600;fill:var(--accent)}}
.undrawn rect{{stroke:var(--line);stroke-dasharray:6 5}}.undrawn text{{fill:var(--muted)}}
.foundation{{opacity:.6}}.band{{fill:var(--faint);stroke:var(--line);stroke-dasharray:3 4}}.band-title{{font-size:12px;font-weight:700;letter-spacing:.08em;fill:var(--muted)}}
.group{{fill:var(--card);stroke:var(--line)}}.group-name{{font-size:13px;font-weight:600}}
.toolbar{{display:flex;flex-wrap:wrap;gap:8px}}.toolbar button{{font:inherit;font-size:.9rem;padding:6px 12px;border-radius:99px;border:1.5px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer;display:inline-flex;align-items:center;gap:6px}}
.toolbar button i{{width:12px;height:12px;border-radius:50%;background:var(--c)}}.toolbar button[aria-pressed=true]{{border-color:var(--fg);font-weight:600}}
.legend{{display:flex;flex-wrap:wrap;gap:8px 20px;padding:0;list-style:none;color:var(--muted);font-size:.9rem}}.sw{{display:inline-block;width:22px;height:14px;margin-right:6px;vertical-align:-2px;border:2px solid var(--n);background:var(--node)}}
.sw.pill{{border-radius:8px}}.sw.rect{{border-radius:3px}}.sw.diamond{{width:13px;height:13px;transform:rotate(45deg);margin:0 10px 0 4px}}.sw.dotted{{border-style:dashed}}.sw.faded{{opacity:.45;border-style:dotted}}
.module-list{{padding-left:18px}}.module-list li{{margin:6px 0}}.module-list a{{font-weight:600}}details{{margin:16px 0}}summary{{cursor:pointer;font-weight:600}}.index li{{margin:4px 0}}
dialog{{width:min(720px,calc(100vw - 24px));max-height:calc(100vh - 48px);border:1px solid var(--line);border-radius:14px;background:var(--bg);color:var(--fg);padding:20px 24px}}
dialog::backdrop{{background:rgb(0 0 0 / .45)}}.close{{float:right;font-size:1.6rem;line-height:1;border:0;background:none;color:var(--fg);cursor:pointer}}
.card{{border:1px solid var(--line);border-radius:12px;background:var(--card);padding:14px 18px;margin:14px 0}}.card h3{{margin:2px 0;font-size:1rem;word-break:break-all}}
.role{{font-size:1.05rem;margin:6px 0 10px}}dl{{margin:0;display:grid;grid-template-columns:minmax(110px,auto) 1fr;gap:6px 14px}}dt{{font-weight:600;color:var(--muted);font-size:.9rem}}dd{{margin:0}}dd ul{{margin:0;padding-left:18px}}
.breaks{{font-weight:600}}.c-owner{{color:var(--v0)}}.c-helper{{color:var(--v2)}}.c-shared_system{{color:var(--v3)}}.files li{{margin:2px 0}}
.pill-tag{{display:inline-block;margin:4px 0;padding:2px 10px;border:1.5px dashed var(--note-line);border-radius:99px;font-size:.85rem}}
@media (max-width:560px){{h1{{font-size:1.4rem}}dl{{grid-template-columns:1fr}}dialog{{padding:16px}}}}"""

JS = """
const views=[...document.querySelectorAll('main [data-view]')],panel=document.getElementById('panel'),body=document.getElementById('panel-body');
const find=(a,v)=>[...document.querySelectorAll('#store ['+a+']')].find(e=>e.getAttribute(a)===v);
let current='overview';
function show(v){current=v;views.forEach(s=>s.hidden=s.dataset.view!==v);}
function openPanel(el,isStage){body.replaceChildren(el.cloneNode(true));
 if(isStage)el.querySelectorAll('li[data-file]').forEach(li=>{const c=find('data-card',li.dataset.file);if(c)body.append(c.cloneNode(true));});
 if(!panel.open)panel.showModal();panel.scrollTop=0;}
function route(){const h=decodeURIComponent(location.hash.slice(1))||'overview',i=h.indexOf('/'),kind=h.slice(0,i),id=h.slice(i+1);
 if(kind==='s'||kind==='f'){const el=find(kind==='s'?'data-stage':'data-card',id);if(!el)return;
  if(kind==='s')show('m/'+el.dataset.module);else if(!views.some(v=>!v.hidden))show('overview');openPanel(el,kind==='s');return;}
 if(panel.open)panel.close();show(views.some(v=>v.dataset.view===h)?h:'overview');window.scrollTo(0,0);}
panel.addEventListener('close',()=>{if(/^#[sf]\\//.test(location.hash))history.replaceState(null,'','#'+current);});
document.addEventListener('click',e=>{const n=e.target.closest('.node');if(n)location.hash='s/'+n.dataset.stage;
 const b=e.target.closest('.toolbar button');if(!b)return;const svg=b.closest('.workflow').querySelector('svg.plate'),v=b.dataset.variant;
 b.parentNode.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',x===b));
 svg.querySelectorAll('[data-v]').forEach(el=>el.classList.toggle('dim',!!v&&el.dataset.v!=='*'&&!el.dataset.v.split(' ').includes(v)));});
document.addEventListener('keydown',e=>{const n=e.target.closest&&e.target.closest('.node');if(n&&(e.key==='Enter'||e.key===' ')){e.preventDefault();n.click();}});
window.addEventListener('hashchange',route);route();
"""
