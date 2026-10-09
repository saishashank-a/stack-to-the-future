---
name: stack-to-the-future
description: Map a codebase into an "anatomy atlas" - plain-language business workflow diagrams per module, with source files as labels on each stage, a card per file, a faded foundation layer for plumbing, and dotted marks for unfinished code. Use when the user asks to map, explain, document or onboard onto a repository's workflows, or runs /stack-to-the-future.
---

# Stack to the Future

> Where we're going, we don't need docs.

**Status: milestone (c).** Scan, draft and validate work. The human checkpoint, caching and rendering are not built yet.

`ATLAS` below means `uv run --script <skill-base-dir>/scripts/atlas.py`, using `scripts/atlas.py` from this skill's base directory. `<root>` is the repository (the user's path, default the current directory).

## Workflow

1. **Preflight.** Check `uv --version`; if missing, tell the user to install it from https://docs.astral.sh/uv/ and stop. If `<root>/.atlas/atlas.json` exists this is a re-run: read it. Tell the user everything stays local in `<root>/.atlas/`.
2. **Scan.** `ATLAS scan <root> [--draft-limit 8]` writes `.atlas/scan.json` (facts + clusters) and `.atlas/.gitignore`. Report the printed summary.
3. **Cluster.** Done inside `scan`: `scan.json` → `clusters` holds modules with a suggested role, workflow skeletons, shared-system candidates, foundation groups and `draft_now`.
4. **Draft.** Follow `templates/draft_instructions.md` exactly. Read source only through `ATLAS excerpt <path> <start> <end> --root <root>` (redacted, line-numbered; secrets files are refused). Write `<root>/.atlas/draft.json`. With several modules in `draft_now`, you may give each module to a subagent along with the same instructions, then combine their sections into one draft.
5. **Validate.** `ATLAS validate <root>/.atlas/draft.json --root <root>`. It prints a numbered list `[rule] /json/pointer: reason`. Fix exactly those items and validate again. Maximum 3 rounds; after that, drop what still fails, add a flag saying what could not be drawn, validate once more, and tell the user what was dropped.

Then stop: show the user a short outline (modules → workflows → stages, with branches and flags) and say the confirm/correct checkpoint, caching and diagrams arrive in later milestones (PLAN.md section 3, steps 6-10).

## Reading scan.json

- `entry_points`, `status_machines`, `permission_branches`, `models`, `incomplete`: facts with file paths and line numbers.
- `symbols`: every function, method, class and assignment with its lines. Evidence `symbol` values must come from here.
- `clusters.modules`: one per top-level package or app folder, with a suggested `role`.
- `clusters.workflows`: skeletons to name in business language; merge or split as the code demands.
- Framework-specific wiring (router prefixes, `Depends`, Celery tasks sent by name) is not resolved until the adapters milestone; read the excerpt when a link looks missing.

## Walkthroughs (on demand)

Never generated upfront. Trigger: "walk me through <file>", "explain <file> step by step", "what does <file> do", `/stack-to-the-future walkthrough <file>`.

1. If `<root>/.atlas/scan.json` is missing or older than the file, run `ATLAS scan <root>` first. A walkthrough works without `atlas.json`, but the card and stages make it better.
2. `ATLAS walkthrough-context <path> --root <root>`: the file's card, the stages it serves, its symbols with lines, who calls it and what it calls, status changes, permission checks, incomplete code, and the redacted source with line numbers. Secrets files are refused; say so and stop.
3. Write `<root>/.atlas/walkthroughs/<path>.md` following `templates/walkthrough.md` exactly, from that context only.
4. `ATLAS check-walkthrough <root>/.atlas/walkthroughs/<path>.md --root <root>`. Fix exactly the listed items and check again, up to 3 rounds; if a claim still can't be cited, remove it.
5. Tell the user the path and give a three-line summary. Don't paste the whole walkthrough unless asked.
