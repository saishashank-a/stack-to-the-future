# Draft instructions

You turn `.atlas/scan.json` into `.atlas/draft.json`: one complete document matching `schema/atlas.schema.json`. The validator checks every rule below; follow them and it passes first time.

**Inputs you may use:** `scan.json` (facts + `clusters`), and source lines from `atlas.py excerpt <path> <start> <end> --root <repo>` (already redacted). Never open files directly, never open secrets files, never copy a value that looks like a password or token.

**Read first:** `references/plain-language.md`, `references/contribution-types.md`, `references/layout.md`.

## 1. Order of work

1. Read `clusters`: modules and their `role`, workflow skeletons, `shared_candidates`, `foundation`, `draft_now`.
2. For each module in `clusters.draft_now` with role `business`, for each workflow skeleton: excerpt its entry points, the functions in `symbols`, its `status_machines`, `permission_branches` and `incomplete` lines. Understand the flow before naming anything.
3. Write the draft (section 2). Then run `atlas.py validate .atlas/draft.json --root <repo>` and fix exactly what it lists.

## 2. What to write

Top level: `atlas_version: "0.1"`, `project` (`name`, plain one-paragraph `summary`, `generated_at` now in UTC ISO 8601, `scanner_version` = scan's `scan_version`, `languages`, `frameworks` from `external_imports`), then every section below. Every object you author gets `"provenance": "claude"`.

### files
Exactly the scan's `files`: same `path`, `sha256`, `language`, `loc`. `layer` starts from the scan's `hint` (business / foundation / ignored); you may move a file between layers when the code clearly says otherwise. `module` = the cluster module id for business files of drawn modules.

### modules
One per business module (skeletons from shared or foundation cluster modules are not modules). `id` = cluster id, `name` = what the business calls it ("Time off", not "leave"), plain `summary`, `files` = its business files, `entry_points` from scan (`kind`, a readable `label`, evidence at the entry point's lines with its `symbol`), `workflows`. Modules not in `draft_now`: still list them with `"drawn": false`, a one-line summary, their files, and `"workflows": []`.

### workflows (one plate each)
A skeleton is a hint. Merge skeletons that are one business process, split one that is two. Then:

- **stages**: business steps. `name` per plain-language.md (who + verb + what, max 60 characters, no code, no banned words, in name *or* description). `kind`: exactly one `start`, at least one `end`, `decision` where the flow splits. `actor`: a role or "System". `files`: each file doing the work, with `contribution` and a `label` that names the code (`"service.py: choose_route"`): identifiers live only here.
- **paths**: arrows `from` → `to`, `label` for decision answers ("approved", "1 day or less"). `variants: []` for the shared trunk.
- **variants**: when one decision sends the same request down different routes that later rejoin (approval vs self-approval vs automatic), keep them on **this one plate**. Each variant has a `condition` in plain words and a `route` of stage ids that follows existing paths, **starts at a stage on the trunk or in another route** (usually the decision) and **ends on one too** (where the routes merge). Every path a variant travels lists that variant id. A plain yes/no that ends the flow (declined) is a path with a label, not a variant.
- **status machines**: each transition in `scan.status_machines` should appear as a path or stage. A state nothing reaches (`incomplete` kind `missing_transition`) becomes a stage with `"status": "incomplete"` reached by a path with `"status": "incomplete"`, plus a flag.
- **permission branches** are usually decisions or the reason a stage has an actor; mention the rule in the description.
- Stage and path ids: `<workflow-id>/<slug>`; variant ids `<workflow-id>/<slug>`.

### links
Cross-module handoffs for the overview: `from_stage` in one workflow, `to_stage` in another, plain `label`, evidence on both sides (the code that writes and the code that reads).

### cards
Exactly one per file whose layer is `business`, none for others. `role`: one plain line (max 140 characters). `stages`: every stage listing this file. `contribution`: the type it has on most of those stages. `receives` / `hands_off`: plain nouns ("a submitted request") with `from_or_to` a file path, stage id, or outside party ("the employee", "the mail server"). `if_removed`: what a user would notice, never "ImportError". `evidence`: the file's main symbols' lines. `source_sha256` = the file's hash.

### shared_systems
From `clusters.shared_candidates` plus anything used by stages in more than one workflow: plain `name`, `files`, `used_by_stages`, evidence.

### foundation
From `clusters.foundation`: one group per key, a plain `label` ("Settings", "Database connection"). Every `foundation` file in exactly one group.

### flags
One per scan `incomplete` item in drawn modules: `kind` (`todo`, `stub`, `not_implemented`, `missing_transition`), plain `message`, `target` (the stage it affects, else the file), evidence at its lines. Also `dead_end` / `unreachable` for any stage you cannot connect (the validator accepts an orphan stage only if it is flagged).

## 3. Evidence rules (the validator rejects anything else)

- Every stage, path, variant, link, card, shared system, flag and entry point cites at least one `{path, start_line, end_line, symbol?}`.
- `path` is a scanned file, lines are within it.
- `symbol`, when given, is a name from `scan.symbols` **for that file** (`"LeaveStatus.APPROVED"`, `"_approve"`, `"Settings.smtp_password"`) and the cited lines overlap that symbol's lines. Lines inside a function body may cite the function. Module-level code (a schedule dict, a router) is cited without `symbol`.
- Never cite a line you have not excerpted.

## 4. Re-runs

If `.atlas/atlas.json` exists, start from it. Anything with `"locked": true` was corrected by a human: copy it unchanged. Redo only items that cite a file whose hash changed, and items for new files.

## 5. When validation fails

Fix exactly the listed items and validate again, at most 3 rounds. Anything still failing after round 3: remove it and add a flag (`dead_end` / `unreachable` for stages, otherwise a `todo` flag on the file) whose message says what could not be drawn, and tell the user.
