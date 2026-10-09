# `.lal` format, version 0.1 (proposed)

`.lal` is the scene format for **Sir Lines-a-Lot**, a hand-drawn diagram canvas. This project proposes it; Lines-a-Lot adopts it. Until then Stack to the Future owns this spec and `schema/lal.schema.json` is the contract.

A `.lal` file is UTF-8 JSON. Everything is plain data: no code, no external references, no embedded images. Coordinates are canvas pixels on one infinite canvas, origin top-left, y grows downward. All coordinates are absolute, so a reader can draw an element without looking up its frame.

## Top level

| Key | Type | Meaning |
|---|---|---|
| `lal_version` | `"0.1"` | Format version. Readers reject a major version they don't know. |
| `title` | string | Scene name, shown in the canvas title bar. |
| `generator` | string | What wrote the file, e.g. `stack-to-the-future`. |
| `layers` | array | Drawing layers, bottom to top. |
| `frames` | array | Named regions of the canvas (a plate, the overview). |
| `nodes` | array | Boxes with text. |
| `connectors` | array | Lines and arrows between nodes. |
| `callouts` | array | Sticky notes attached to a node (or to a frame when `target` is null). |
| `legends` | array | Per-frame colour keys. |

## Layers

`{ "id", "name", "opacity" }`. `opacity` is 0 to 1 and multiplies everything on the layer. Stack to the Future writes three: `business` (1.0), `foundation` (0.4, the faded plumbing) and `annotations` (1.0, callouts and their tethers). Every node, connector and callout names its `layer`.

## Frames

`{ "id", "kind", "title", "x", "y", "width", "height" }`. `kind` is `overview` or `plate`. Frames don't nest. A canvas should offer frame-to-frame navigation (an outline or a minimap).

## Nodes

```json
{
  "id": "stage:request-time-off/submit",
  "frame": "request-time-off",
  "layer": "business",
  "shape": "pill",
  "x": 50, "y": 478, "width": 180, "height": 68,
  "label": "Employee asks for time off",
  "caption": "Employee",
  "sublabels": ["routes.py: submit_leave", "service.py: submit_request"],
  "style": { "stroke": "solid", "color": "#495057", "fill": null },
  "link": null,
  "source": { "kind": "stage", "id": "request-time-off/submit" }
}
```

- `shape`: `rect`, `pill` (start/end), `diamond` (decision), `note` (a group box, such as a shared system or foundation group) or `band` (a background region).
- `label` is the main text and may contain `\n`. `caption` is small text above the box (who does it). `sublabels` are the small monospace lines under the box: the "bone labels" naming the code behind it.
- `style.stroke`: `solid`, `dashed` (not built yet) or `dotted`. `style.color` is a `#rrggbb` stroke colour; `style.fill` is `#rrggbb` or null.
- `link`: a frame id to open when the node is clicked (the overview links each module to its first plate), or null.
- `source` points back into the generator's own data. Lines-a-Lot can ignore it; Stack to the Future uses it to preserve edits.

## Connectors

```json
{
  "id": "path:request-time-off/p-route-direct",
  "frame": "request-time-off",
  "layer": "business",
  "from": "stage:request-time-off/choose-route",
  "to": "stage:request-time-off/approve-directly",
  "label": "1 day or less",
  "points": [[510, 512], [540, 512], [540, 302], [590, 302]],
  "style": { "stroke": "solid", "color": "#1c7ed6", "width": 2, "arrow": "end" },
  "group": "request-time-off/direct",
  "source": { "kind": "path", "id": "request-time-off/p-route-direct" }
}
```

- `points` is the drawn polyline, at least two points, the first on `from` and the last on `to`. A canvas may re-route a connector when its nodes move, as long as it stays attached to `from` and `to`.
- `group` names a route (a variant). Connectors in the same group share a colour and can be highlighted together; null means the shared trunk.
- `style.arrow`: `end` or `none`.

## Callouts

`{ "id", "frame", "layer", "target", "kind", "text", "x", "y", "width", "height" }`. `target` is a node id or null (the note is about the whole frame). `kind` is free text such as `todo`, `missing_transition` or `not_implemented`. A canvas draws a light tether from the callout to its target.

## Legends

`{ "frame", "entries": [{ "id", "label", "detail", "color" }] }`: the variant colours of one plate, e.g. "Self-approval: when a manager asks for 3 days or less".

## Compatibility rules

- Readers ignore unknown keys. Writers never put meaning in key order.
- Ids are unique across the whole file. Every `from`, `to`, `target`, `frame`, `layer` and `link` reference resolves.
- Text is plain text. Readers never interpret it as HTML or markup.
