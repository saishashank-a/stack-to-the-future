# Stack to the Future: Plan

> *Where we're going, we don't need docs.*

Status: **open questions resolved (section 10), awaiting final approval**. No feature code until this is signed off.

## 0. What the skill produces

An **anatomy atlas** of a codebase, stored as `.atlas/atlas.json` and rendered to diagrams.

- **Level 1, Anatomy.** One business workflow diagram ("plate") per module, written in plain language a non-technical reader can follow. Variants of a flow (approval, self-approval, direct) are **branches on one diagram that merge back**, never separate diagrams. A **full-body overview** shows every module and how they hand off to each other, and each module links to its plate.
- **Level 2, Function.** Every file gets a card: one-line role, the stages it serves, contribution type (**Owner, Helper, Shared system, Foundation**), what it receives, what it hands off, and *what breaks if this file is gone*. A step-by-step **walkthrough** of a single file is generated on demand, never upfront.
- **Foundation layer.** Plumbing (imports, config, DB setup, secrets loading, requirements) is grouped into a faded layer under the plates.
- **Incomplete code.** Stubs, TODOs and missing transitions are flagged and drawn dotted.

Code shows up only as labels on stages, like labelled bones on an anatomy chart.

### Key design decision: Claude is the LLM

The skill runs inside Claude Code, so the "LLM step" is Claude itself reading `scan.json` plus redacted source excerpts and writing a draft. **No API key, no network calls, no model SDK.** Python scripts do everything deterministic (scan, cluster, validate, redact, cache, render). For large repos, SKILL.md tells Claude to fan out one subagent per module.

---

## 1. Skill folder layout

```
stack-to-the-future/                  # this repo = a Claude Code plugin
├── .claude-plugin/
│   ├── plugin.json                   # plugin manifest (name, version, description, author)
│   └── marketplace.json              # single-plugin marketplace so `/plugin install` works from this repo
├── commands/
│   └── stack-to-the-future.md        # /stack-to-the-future slash command, hands off to the skill
├── skills/stack-to-the-future/       # the skill itself
│   ├── SKILL.md                      # the workflow Claude follows (section 3)
│   ├── scripts/
│   │   ├── atlas.py                  # single CLI entry: scan (incl. cluster) | validate | merge | render | walkthrough-context
│   │   ├── scan.py                   # tree-sitter parse -> symbols, imports, calls, detections
│   │   ├── graph.py                  # networkx import + call graph, entry-point reachability
│   │   ├── cluster.py                # modules + workflow skeletons from graph and detections
│   │   ├── validate.py               # JSON Schema + evidence checks (section 2.3)
│   │   ├── redact.py                 # secret detection and scrubbing (section 6)
│   │   ├── cache.py                  # per-file hash cache (keyed by content hash + scanner version)
│   │   ├── checkpoint.py             # merge with locked corrections, stale, outline
│   │   └── render/
│   │       ├── html.py               # single self-contained HTML file (no CDN)
│   │       ├── excalidraw.py         # .excalidraw JSON
│   │       └── lal.py                # .lal export, reads only atlas.json (section 5)
│   ├── schema/
│   │   ├── atlas.schema.json         # source-of-truth schema (section 2)
│   │   └── scan.schema.json          # deterministic scan output
│   ├── templates/
│   │   ├── draft_instructions.md     # what Claude must produce for stages + cards
│   │   ├── outline.md                # human-checkpoint outline format
│   │   ├── walkthrough.md            # on-demand file walkthrough format
│   │   └── atlas.html                # HTML renderer shell
│   ├── references/
│   │   ├── lal-format.md             # proposed .lal spec (section 5), owned here until Lines-a-Lot adopts it
│   │   ├── plain-language.md         # style guide: business verbs, no jargon, banned words
│   │   ├── contribution-types.md     # Owner / Helper / Shared system / Foundation definitions + examples
│   │   └── layout.md                 # how branches/merges, foundation layer and dotted flags are drawn
│   └── adapters/
│       ├── base.py                   # adapter protocol (section 7)
│       ├── fastapi.py
│       ├── celery.py
│       ├── sqlalchemy.py
│       └── nextjs.py
├── examples/
│   └── leave-desk.atlas.json         # hand-written sample atlas (milestone a)
├── fixtures/
│   └── leave-desk/                   # toy repo we write ourselves (section 8)
├── tests/
├── PLAN.md
├── README.md
├── LICENSE
└── THIRD_PARTY_LICENSES.md
```

Scripts use **PEP 723 inline dependency metadata** and run with `uv run`, so the skill has no separate install step and doesn't touch the target project's environment. **`uv` is required**; SKILL.md preflight checks for it and prints the one-line install if missing. Python 3.11+.

Install: `/plugin marketplace add saishashank-a/stack-to-the-future` then `/plugin install stack-to-the-future`. For local development, `claude --plugin-dir .`.

Working files inside the **target** repo:

```
.atlas/
├── atlas.json          # source of truth (commit)
├── scan.json           # deterministic facts (regenerable, gitignored)
├── draft.json          # Claude's draft before validation + checkpoint (gitignored)
├── cache/<sha256>.json # per-file scan facts + card, keyed by content hash (gitignored)
├── walkthroughs/       # on-demand file walkthroughs (<path>.md, commit)
├── out/                # atlas.html, atlas.excalidraw, atlas.lal (commit)
└── .gitignore          # written by the skill: scan.json, draft.json, cache/
```

`atlas.json` and `out/` are redacted and human-confirmed, so they're safe to commit; the skill writes `.atlas/.gitignore` itself so the target repo needs no edits.

---

## 2. `atlas.json` schema

### 2.1 Shape

| Section | What it holds |
|---|---|
| `project` | name, languages, frameworks detected, scanner version, generated_at |
| `modules` | business areas (e.g. "Leave requests"), their files, workflows, entry points |
| `workflows` | one per plate: `stages`, `paths`, `variants` |
| `stages` | a business step: plain name, description, actor, kind (start/step/decision/end), files with contribution, status |
| `paths` | arrows between stages: from, to, condition, which variants travel it, status |
| `variants` | named branches (approval / self-approval / direct) with condition and ordered route; all live on one diagram |
| `links` | cross-module handoffs, used by the full-body overview |
| `files` | every scanned file: path, hash, language, layer (business/foundation/ignored) |
| `cards` | Level 2 file cards |
| `shared_systems` | cross-cutting services used by many stages (email, audit log, auth) |
| `foundation` | grouped plumbing: Configuration, Database setup, Secrets loading, Dependencies, Wiring |
| `flags` | incomplete code: stub, todo, missing_transition, dead_end, unreachable, stale_override |

Every LLM- or human-authored object carries:
- `evidence`: one or more `{path, start_line, end_line, symbol?}` citations
- `provenance`: `scan` | `claude` | `human`
- `locked`: `true` once a human corrects it (re-runs never overwrite locked fields)

IDs are stable slugs (`leave-requests/manager-review`), file IDs are repo-relative POSIX paths, so re-runs and human edits line up.

### 2.2 JSON Schema (draft 2020-12)

The schema lives in [`skills/stack-to-the-future/schema/atlas.schema.json`](skills/stack-to-the-future/schema/atlas.schema.json), which is the source of truth. It was moved out of this plan in milestone (a) so the two can't drift apart.

### 2.3 Validator rules (beyond the schema)

`validate.py` rejects the draft, with a precise error list Claude must fix, if any of these fail:

1. Every `evidence.path` exists in `scan.json`; `start_line <= end_line <= file line count`.
2. Every `evidence.symbol` exists in the scan symbol table **for that file**, and its definition overlaps the cited range.
3. Every slug referenced (stages, paths, variants, links, cards, shared systems) resolves.
4. Every `business` file has exactly one card; every `foundation` file appears in exactly one foundation group.
5. Each variant's `route` follows existing `paths` and starts and ends on stages shared with at least one other variant (branches must merge).
6. Each workflow has one `start`, at least one `end`, and no orphan stages; violations become `dead_end` / `unreachable` flags rather than silent drops.
7. Stage names pass the plain-language lint (`references/plain-language.md`): no file names, no code identifiers, no banned jargon (`endpoint`, `ORM`, `handler`, ...). Identifiers belong in `stageFile.label` only.
8. Redaction pass is clean (section 6).
9. Each card's `stages` equals the set of stages whose `files` list that file (added in (c)).
10. `files[]` matches `scan.json` paths and hashes; ids are unique (added in (c)).

---

## 3. SKILL.md workflow (what Claude does, step by step)

Trigger: "map this codebase", "make an atlas", "explain this repo's workflows", `/stack-to-the-future`.

1. **Preflight.** Confirm repo root. Read `.atlas/atlas.json` if present (re-run mode). Tell the user outputs stay local in `.atlas/`.
2. **Scan.** `uv run scripts/atlas.py scan .` → `.atlas/scan.json`. Only files whose hash changed are re-parsed. Adapters run here. Report counts: files, entry points, state machines, jobs, models, TODOs.
3. **Cluster.** Runs inside `scan` (cheap and deterministic, so no separate command) → module and workflow skeletons (entry points + reachable files + detected status transitions), foundation files pre-sorted.
4. **Draft (Claude).** Follow `templates/draft_instructions.md`. For each workflow skeleton, read the cited excerpts (`atlas.py excerpt <path> <start> <end>`, which is redacted) and write `.atlas/draft.json`: stage names in business language, variants as branches that merge, files mapped to stages with contribution type, file cards. Only touch items that are new or stale; never edit `locked` items. Large repos (more than `--draft-limit` modules, default 8): scan everything, draft the top modules ranked by entry-point count, and list the rest on the overview as *not yet drawn* (`modules[].drawn: false`); "draw the Billing module" drafts one on request. Several modules to draft: one subagent per module, each writes a module fragment, then `atlas.py merge` combines them.
5. **Validate.** `uv run scripts/atlas.py validate .atlas/draft.json`. On failure, fix exactly the reported items and re-run. Max 3 rounds; anything still failing is dropped and turned into a flag, and the user is told.
6. **Human checkpoint.** Render `templates/outline.md`: modules → workflows → stages (with variant branches and merges), shared systems, foundation groups, flags. Ask the user to confirm or correct. Corrections are applied with `provenance: human, locked: true`. Repeat until confirmed.
7. **Commit atlas.** `atlas.py merge --approve` writes `.atlas/atlas.json` (and updates `cache/`).
8. **Render.** `atlas.py render --format lal,excalidraw,html` → `.atlas/out/`. Default is all three; HTML is the one to open first.
9. **Report.** Paths to outputs, flag count with the top items, and how to ask for a walkthrough.
10. **On demand: walkthrough.** "Walk me through `services/approval.py`" → `atlas.py walkthrough-context <path>` gives the card, the stages it serves, redacted source, and callers/callees. Claude writes `.atlas/walkthroughs/<path>.md` following `templates/walkthrough.md`, citing line ranges, and the validator checks its citations.

---

## 4. Pipeline details

| Step | Deterministic? | Tooling | Output |
|---|---|---|---|
| 1. Static scan | yes | `tree-sitter` + `tree-sitter-python`, `networkx` | `scan.json` |
| 2. Cluster | yes | `networkx` (reachability from entry points, community detection as tiebreak) | skeletons in `scan.json` |
| 3. Draft | no (Claude) | templates + references | `draft.json` |
| 4. Validate | yes | `jsonschema` + custom rules | pass / error list |
| 5. Checkpoint | human | outline | corrections |
| 6. Output | yes | renderers | `atlas.json`, `out/*` |
| 7. Re-run | yes | `cache.py` | only changed work redone |

**Static scan detects:**
- **Entry points:** decorated route functions, CLI commands (`argparse`, `click`, `typer`), `if __name__ == "__main__"`, UI pages (via adapters).
- **Status enums and transitions:** `Enum` subclasses with status-like names/members; assignments `x.status = Status.APPROVED` inside functions → (from, to) edges when the guarding condition reads the current status.
- **Role / permission branches:** conditionals that test `role`, `is_admin`, `has_perm`, `user.id == ...owner_id` and similar; recorded as decision candidates.
- **Background jobs:** Celery tasks, `BackgroundTasks.add_task`, schedulers (via adapters).
- **Data models:** SQLAlchemy / dataclass / Pydantic classes and their fields (names only).
- **Incomplete code:** `pass`/`...`-only bodies, `raise NotImplementedError`, `TODO|FIXME|XXX` comments, enum states with no incoming or outgoing transition.
- **Foundation candidates:** config modules, settings classes, engine/session setup, `.env` loaders, `requirements*.txt` / `pyproject.toml`, `__init__.py` re-exports.

**Cluster:** module = **top-level package or app folder** (e.g. `app/leave/`, `app/reports/`; for a flat single-package repo, its direct subpackages; for a repo with no packages, one module). Predictable and matches how the code is laid out; you rename, merge or split modules at the checkpoint and that is locked. Within a module, workflows = entry points plus the files reachable from them and any status machine they drive. Files reached from more than one module become shared-system candidates; foundation-tagged files are pulled out first so they don't glue modules together.

**Re-runs and corrections:**
- Cache key = sha256 of file content. Unchanged file → reuse cached scan facts and card.
- Changed file → re-scan; its card and every stage/path whose evidence cites it are marked stale and re-drafted.
- `locked` (human) fields are never overwritten. If a locked item's evidence no longer resolves, keep it and raise a `stale_override` flag at the checkpoint instead of deleting it.
- Deleted file → its card is removed; stages that relied only on it become flagged.

---

## 5. Renderers

All renderers read **only** `atlas.json`. None import from each other or from the scanner.

- **`.lal` (primary).** `render/lal.py` maps atlas concepts to Sir Lines-a-Lot primitives: plate = canvas/frame, stage = node, path = connector (dashed when `incomplete`), variant = connector colour + legend, foundation = faded band, flag = callout. The mapping lives in that one file, so this project never depends on Lines-a-Lot internals; if the `.lal` format changes, only `lal.py` changes. **This project proposes the `.lal` spec** in `references/lal-format.md` (milestone e): versioned JSON with `frames` (plates + overview), `nodes` (id, label, kind, position, style), `connectors` (from, to, label, dash, colour), `layers` (business / foundation with opacity), `callouts` (flags), and `links` (node → frame, for overview click-through). Lines-a-Lot adopts it later; until it can open `.lal`, the HTML file is the primary viewable output.
- **Excalidraw (fallback).** Plain `.excalidraw` JSON with `roughness` set for the hand-drawn look; one frame per plate plus an overview frame.
- **HTML (fallback).** One self-contained file: inline CSS, inline JS, inline SVG, no CDN, works offline. Overview → click a module → plate → click a stage → its file cards. Foundation faded at the bottom, flags dotted, variants toggleable to highlight one route at a time.

Layout (shared helper, deterministic): left-to-right lanes, trunk on the centre line, variant branches above/below, merging back into the shared stage. Hand-rolled layered layout first; add a layout library only if it falls short.

---

## 6. Security

- **Never extract values.** The scanner records identifiers only (`DATABASE_URL`, `STRIPE_KEY`), never the literal assigned to them. String literals are not stored in `scan.json` at all.
- **Skip secret files.** `.env*`, `*.pem`, `*.key`, `id_*`, `*.p12`, `secrets.*`, `credentials*` are recorded by name only, never read.
- **Redaction pass** (`redact.py`) runs on (a) every excerpt shown to Claude, (b) the draft, (c) every rendered output before it's written:
  - known token formats (AWS, GitHub, Slack, Stripe, Google, JWTs, private-key blocks, connection strings with credentials),
  - high-entropy strings assigned to names matching `key|secret|token|password|passwd|credential|auth|dsn`,
  - replaced with `[REDACTED:<kind>]`. Any hit in a final output fails the render.
- **Local by default.** Everything goes to `.atlas/`. No network calls. Sharing is the user's explicit choice.

---

## 7. Framework adapters

Adapters add facts static analysis misses. They run during scan, emit facts in the same `scan.json` shape, and never call Claude.

```python
class Adapter(Protocol):
    name: str
    def applies(self, project: ProjectIndex) -> bool: ...          # e.g. 'fastapi' in deps or imports
    def extract(self, project: ProjectIndex) -> list[Fact]: ...    # EntryPoint | CallEdge | Model | Transition | Job | Permission
```

Discovery: every module in `adapters/` exposing `ADAPTER` is loaded. Adding a framework = one new file plus a fixture test. No registry, no plugin system.

| Adapter | Facts |
|---|---|
| **FastAPI** | `APIRouter` + `include_router` prefixes resolved to full routes; `Depends(...)` chains as call edges (auth deps → permission facts); middleware as foundation/wiring; `BackgroundTasks.add_task` as jobs |
| **Celery** | `@app.task` / `@shared_task` definitions; `.delay`, `.apply_async`, `send_task("name")` dispatch resolved by task name to call edges; beat schedules as scheduled entry points |
| **SQLAlchemy** | declarative models and columns (names only); `relationship`s; `@event.listens_for` hooks as call edges; enum-typed status columns linked to status enums |
| **Next.js App Router** | `app/**/page.tsx` → UI pages, `app/**/route.ts` → route handlers with HTTP verbs, layouts as wiring, server actions as entry points. Uses `tree-sitter-typescript` **only inside this adapter**; v1 has no general JS/TS scanner, so TS files outside the adapter's patterns are listed as files but not analysed |

---

## 8. Test fixture

**`fixtures/leave-desk/`, a toy repo we write ourselves.** Small (~25 files) FastAPI + SQLAlchemy + Celery app for leave requests, built to exercise every feature:

- Submit → (manager approval | self-approval for managers | direct approval under 1 day) → record balance → notify, so three variants branch and merge on one plate.
- A second module (Reports) that receives approved leave, so the overview has a cross-module link.
- Shared systems: email notifications, audit log.
- Foundation: settings, DB session, `.env` loading, `requirements.txt`.
- Planted incomplete code: a `Cancelled` status with no transition in, a `NotImplementedError` export stub, a TODO.
- Planted **fake** secrets (obviously fake, e.g. `sk_test_FAKEFAKE...`) to prove redaction.
- `examples/leave-desk.atlas.json` is the hand-written expected atlas, used as the golden file.

Later, a Next.js slice is added to the fixture for the Next.js adapter.

Secondary smoke test (not vendored, cloned at test time, nothing committed): a permissively licensed public repo such as `fastapi/full-stack-fastapi-template` (MIT) to check the scanner holds up on real code.

**No proprietary or client code is used as a fixture in this repo.**

---

## 9. Milestones

Each milestone ends with a passing test and a commit; a milestone isn't done until its exit check passes.

| | Milestone | Deliverables | Exit check |
|---|---|---|---|
| **a** | Schema + sample atlas | plugin skeleton (`plugin.json`, `marketplace.json`, command, empty skill), `atlas.schema.json`, `leave-desk` fixture, hand-written `examples/leave-desk.atlas.json`, `references/*.md` | Sample validates against the schema; a human can read it and agree it describes the fixture |
| **b** | Static scanner (Python) | `scan.py`, `graph.py`, `cluster.py`, `redact.py`, `scan.schema.json` | On the fixture: all entry points, status transitions, role branches, jobs, models, planted TODO/stubs found; zero fake secrets in `scan.json` |
| **c** | Draft + validator | `templates/draft_instructions.md`, `validate.py`, SKILL.md steps 1–5 | Claude's draft on the fixture passes validation; a fabricated symbol / out-of-range line / unmerged variant is rejected in tests |
| **d** | Checkpoint + caching | outline template, `cache.py`, merge with `locked` | Edit one fixture file → only its card and dependent stages re-drafted; a human correction survives the re-run; deleted evidence raises `stale_override` |
| **e** | Renderers | `html.py`, `excalidraw.py`, `lal.py` | HTML opens offline and shows overview → plate → card with branches merging and dotted flags; `.excalidraw` opens in excalidraw.com; `.lal` opens in Lines-a-Lot (pending spec) |
| **f** | Adapters | FastAPI, Celery, SQLAlchemy, Next.js | Each adapter's fixture facts appear in `scan.json` (Celery `send_task` by name resolves; router prefixes resolve) |
| **g** | Walkthroughs | `walkthrough-context`, `templates/walkthrough.md` | Walkthrough of a fixture file cites only valid line ranges and passes redaction |

Adapters stay in (f) as listed. Consequence: the (b) scanner is framework-agnostic, so on the FastAPI fixture it finds decorated functions and status transitions but not router prefixes or `Depends` chains. The (b) exit check expects exactly that, and the golden file gains the missing facts in (f).

---

## 10. Decisions (open questions resolved 2026-10-09)

| # | Question | Decision |
|---|---|---|
| 1 | `.lal` format | **This project proposes the spec** in `references/lal-format.md`; Lines-a-Lot adopts it later. HTML is primary viewable output until then. |
| 2 | Distribution | **Claude Code plugin** with `/stack-to-the-future` command and a single-plugin marketplace in this repo. |
| 3 | Runtime | **Require `uv`**; PEP 723 inline deps, no install step. |
| 4 | Language scope | **Python scanner + TS/TSX only inside the Next.js adapter.** No general JS/TS scanning in v1. |
| 5 | FastAPI adapter timing | **Stays in milestone (f).** (b) is framework-agnostic and its exit check is scoped accordingly. |
| 6 | What is a module | **Top-level package / app folder.** Renamed, merged or split at the checkpoint. |
| 7 | Large repos | **Scan all, draft top modules first** (default 8, ranked by entry points); rest shown as *not yet drawn*, drafted on request. |
| 8 | Committing `.atlas/` | **Commit `atlas.json`, `out/`, `walkthroughs/`**; skill writes `.atlas/.gitignore` for `scan.json`, `draft.json`, `cache/`. |
| 9 | Tone | **One plain-language register** for everyone, enforced by the plain-language lint. |

## 11. Notes from implementation

- **(b) tree-sitter is capped below 0.26.** 0.26.0 segfaults while walking some real files (reproduced on `full-stack-fastapi-template` `backend/tests/api/routes/test_users.py`, Python 3.11 and 3.13); 0.25.2 is fine. Lift the cap when a fixed release ships.
- **(b) Workflow skeletons group entry points by file, reachability and shared status machines,** not by shared helper code; shared CRUD/dependency helpers otherwise chain every route into one skeleton on real repos.
- **(b) Module rule on monorepos.** With `backend/` + `frontend/` at the top, each becomes one module, as decided. On the FastAPI template that makes `backend` one module with six workflow skeletons (items, login, users, ...), which the checkpoint can split.
- **(b) SQLModel** classes count as data tables only with `table=True`; the rest are request/response shapes.
- **(c) Validator line bound is `end_line <= loc`.** `loc` is the exact line count (a last line without a trailing newline counts); the earlier `+1` slack is gone.
- **(c) "Never edit locked items" is enforced only by instructions** until `merge` (milestone d) can compare against the previous `atlas.json`.
- **(c) The exit-check draft passed in one round, but was written by the same context that wrote the golden atlas,** so it does not prove the instructions work blind. A fresh-context draft is the real test.
- **(f) Adapters:** routes carry full prefixed paths (settings-driven prefixes shown as `{NAME}`); `Depends`/`dependencies=` become call edges and access checks; Celery `send_task` by name and beat schedules resolve; SQLAlchemy events and enum status columns link up; Next.js App Router via `tree-sitter-typescript` 0.23.2 only inside its adapter. Test app: `fixtures/nextjs-app/`.
- **(f) Known gaps:** no TODO/stub detection in TypeScript.
- **(f) Routers mounted more than once:** the entry point keeps the first full path (sorted) as `path`/`label` and lists the rest in `also_at`; dependencies from every mount are inherited, so a guard on any mount is recorded.
- **(f) Next.js modules:** an `app/` folder holding a `page`/`layout` file is split by first URL segment; route groups `(x)` and `api/` are see-through, and root files plus `_private` folders form the `app` module. Other top-level folders (`lib/`, `components/`) follow the normal rule.
- **(g) Walkthrough citations** are backticked `` `path:start-end symbol` `` (or `` `path:line` ``); `check-walkthrough` reuses the validator's citation check, requires a citation per step, lints prose for code identifiers, and fails on redaction hits.
- **(g) Known gaps:** redaction catches recognisable secret shapes only (a bare value pasted into prose with no context passes, same as the atlas); stale walkthroughs are caught only when `check-walkthrough` reruns. Candidate for the (d) `stale` command.
- **(d) Checkpoint:** `merge` keeps locked items (and a whole previous workflow if the draft drops one holding a locked item), flags locked items whose evidence broke as `stale_override`; the validator tolerates evidence/ref errors only inside stale_override-flagged items. `stale` counts a stage as citing a file if its evidence *or* its file labels name it. `source_sha256` on cards is optional (falls back to the previous atlas's `files[]` hash). Cache facts are redacted before they hit disk; cached and uncached scans are byte-identical (checked after merging with the adapters).
- **(e) Renderers:** secrets are checked twice: on every input string (labels get truncated when drawn, which could cut a secret below pattern length) and on the final output; any hit means nothing is written. File cards appear in HTML only; Excalidraw and `.lal` carry diagrams and bone labels. HTML draws merges as one neutral arrow; Excalidraw/`.lal` keep one bound arrow per branch so they re-route when nodes move. `.lal` v0.1 is specified in `references/lal-format.md`.
- **(e) Known gaps:** the `.excalidraw` file was not imported into excalidraw.com (structure is test-covered only). On phones the leave plate's trunk starts ~450px down under the branch lanes; consider putting the most-used variant below the trunk.
