---
name: stack-to-the-future
description: Map a codebase into an "anatomy atlas" - plain-language business workflow diagrams per module, with source files as labels on each stage, a card per file, a faded foundation layer for plumbing, and dotted marks for unfinished code. Use when the user asks to map, explain, document or onboard onto a repository's workflows, or runs /stack-to-the-future.
---

# Stack to the Future

> Where we're going, we don't need docs.

**Status: milestone (b).** The deterministic scan works. Naming stages, file cards, validation and rendering are not built yet.

## What works now

1. Check `uv` is installed (`uv --version`). If not, tell the user to install it from https://docs.astral.sh/uv/ and stop.
2. Scan the repository root (the user's path, default the current directory), using `scripts/atlas.py` from this skill's base directory:

   ```sh
   uv run --script <skill-base-dir>/scripts/atlas.py scan <root> [--draft-limit 8]
   ```

   This writes `<root>/.atlas/scan.json` and `<root>/.atlas/.gitignore`. Nothing leaves the machine and no secret values are stored.
3. Report the printed summary: entry points, status machines, permission branches, models, incomplete code, and modules with their role (business / shared / foundation).
4. Tell the user the next steps (business-language stages, file cards, diagrams) arrive in later milestones; see PLAN.md section 3.

## Reading scan.json

- `entry_points`, `status_machines`, `permission_branches`, `models`, `incomplete`: facts with file paths and line numbers.
- `clusters.modules`: one per top-level package or app folder, with a suggested `role`.
- `clusters.workflows`: skeletons (entry points grouped by file, call reachability and shared status machines) to be named in business language.
- `clusters.foundation`: plumbing files by group; `clusters.shared_candidates`: likely shared systems.
- Framework-specific wiring (router prefixes, `Depends`, Celery tasks sent by name) is not resolved until the adapters milestone.
