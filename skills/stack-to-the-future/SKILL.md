---
name: stack-to-the-future
description: Map a codebase into an "anatomy atlas" - plain-language business workflow diagrams per module, with source files as labels on each stage, a card per file, a faded foundation layer for plumbing, and dotted marks for unfinished code. Use when the user asks to map, explain, document or onboard onto a repository's workflows, or runs /stack-to-the-future.
---

# Stack to the Future

> Where we're going, we don't need docs.

**Status: milestone (d).** Scan, draft, validate, the human checkpoint and re-runs work. Rendering is not built yet.

`ATLAS` below means `uv run --script <skill-base-dir>/scripts/atlas.py`, using `scripts/atlas.py` from this skill's base directory. `<root>` is the repository (the user's path, default the current directory).

## Workflow

1. **Preflight.** Check `uv --version`; if missing, tell the user to install it from https://docs.astral.sh/uv/ and stop. If `<root>/.atlas/atlas.json` exists this is a re-run (step 9). Tell the user everything stays local in `<root>/.atlas/`.
2. **Scan.** `ATLAS scan <root> [--draft-limit 8]` writes `.atlas/scan.json` (facts + clusters) and `.atlas/.gitignore`. Unchanged files come from `.atlas/cache/`. Report the printed summary.
3. **Cluster.** Done inside `scan`: `scan.json` → `clusters` holds modules with a suggested role, workflow skeletons, shared-system candidates, foundation groups and `draft_now`.
4. **Draft.** Follow `templates/draft_instructions.md` exactly. Read source only through `ATLAS excerpt <path> <start> <end> --root <root>` (redacted, line-numbered; secrets files are refused). Write `<root>/.atlas/draft.json`. With several modules in `draft_now`, you may give each module to a subagent along with the same instructions, then combine their sections into one draft.
5. **Validate.** `ATLAS validate <root>/.atlas/draft.json --root <root>`. It prints a numbered list `[rule] /json/pointer: reason`. Fix exactly those items and validate again. Maximum 3 rounds; after that, drop what still fails, add a flag saying what could not be drawn, validate once more, and tell the user what was dropped.

6. **Checkpoint.** `ATLAS merge <root>/.atlas/draft.json --root <root>` folds in every correction the user locked earlier, writes the result back to `.atlas/draft.json` and prints the outline. Show the user the outline exactly as printed and ask them to confirm or correct it. Do not render anything before they confirm.
7. **Apply corrections.** For each correction, edit that item in `.atlas/draft.json` (find it by the id the user named) and set `"provenance": "human", "locked": true` on it. A rename touches only `name`; moving a file between stages also updates both stages' `files` and the file's card `stages`. Validate (step 5 rules), then repeat step 6 until the user says it looks right. Never set `locked` on anything the user did not correct.
8. **Approve.** `ATLAS merge <root>/.atlas/draft.json --root <root> --approve` validates and writes `.atlas/atlas.json`. If it reports `stale_override` flags, tell the user which of their corrections now describe code that changed and ask whether to keep, update or drop each one.
9. **Re-run.** When `atlas.json` already exists: scan (step 2), then `ATLAS stale --root <root>`. If it says nothing changed, stop. Otherwise copy `atlas.json` to `draft.json`, replace its `files[]` with the scan's, and re-draft **only** the items under "Re-draft"; leave everything else as it is. Items under "Needs human review" are the user's locked corrections: show them to the user and ask, never edit them yourself. Then validate (step 5) and continue from step 6.

Diagrams are not built yet (PLAN.md section 3, step 8 onward); after approval tell the user `atlas.json` is ready and rendering comes in a later milestone.

## Reading scan.json

- `entry_points`, `status_machines`, `permission_branches`, `models`, `incomplete`: facts with file paths and line numbers.
- `symbols`: every function, method, class and assignment with its lines. Evidence `symbol` values must come from here.
- `clusters.modules`: one per top-level package or app folder, with a suggested `role`.
- `clusters.workflows`: skeletons to name in business language; merge or split as the code demands.
- Framework-specific wiring (router prefixes, `Depends`, Celery tasks sent by name) is not resolved until the adapters milestone; read the excerpt when a link looks missing.
