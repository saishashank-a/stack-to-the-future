---
name: stack-to-the-future
description: Map a codebase into an "anatomy atlas" - plain-language business workflow diagrams per module, with source files as labels on each stage, a card per file, a faded foundation layer for plumbing, and dotted marks for unfinished code. Use when the user asks to map, explain, document or onboard onto a repository's workflows, or runs /stack-to-the-future.
---

# Stack to the Future

> Where we're going, we don't need docs.

**Status: milestone (a).** Only the atlas schema and a hand-written sample exist. The scanner, validator and renderers are not built yet.

If invoked now, tell the user the skill is not ready to scan repositories, and point them to:

- `schema/atlas.schema.json`: the atlas format
- `examples/leave-desk.atlas.json` in the plugin repo: what a finished atlas looks like
- `references/`: how stages are named, how files are classified, how plates are drawn

The full workflow (scan → cluster → draft → validate → checkpoint → render) lands in milestones (b) to (g); see PLAN.md section 3.
