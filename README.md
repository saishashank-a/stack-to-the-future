# Stack to the Future

> *Where we're going, we don't need docs.*

A Claude Code skill that scans any codebase, from an enterprise monolith to a student's final-year project, and produces an **anatomy atlas** of it.

The atlas is one business-level workflow diagram per module. The code appears only as labels on each stage, like labelled bones on an anatomy chart:

- **Level 1, Anatomy:** plain-language workflow diagrams a non-technical reader can follow, with a full-body overview linking into each module's plate.
- **Level 2, Function:** a card for every file: its role, the stages it serves, what it receives and hands off, and what breaks if it's gone.
- **Foundation layer:** plumbing (config, DB setup, imports, secrets loading) shown faded underneath.
- **Incomplete code:** stubs and TODOs drawn dotted.

Status: all seven planned milestones are built. Next up: real-world testing.

## See a sample

Open [`examples/out/leave-desk.atlas.html`](examples/out/leave-desk.atlas.html) in a browser (works offline). It is the atlas of [`fixtures/leave-desk`](fixtures/leave-desk), a small time-off app built for testing: three approval routes branching and merging on one diagram, two modules, shared systems, the faded foundation layer and dotted unfinished work. The same atlas is also exported as [Excalidraw](examples/out/leave-desk.atlas.excalidraw) and [`.lal`](examples/out/leave-desk.atlas.lal) ([format](skills/stack-to-the-future/references/lal-format.md)).

## Install

```
/plugin marketplace add saishashank-a/stack-to-the-future
/plugin install stack-to-the-future
```

Requires [uv](https://docs.astral.sh/uv/). Then ask Claude to "map this codebase" or run `/stack-to-the-future`.

## What Claude runs

All scripts are deterministic; Claude only does the naming and writing. Nothing leaves your machine, and secret values never reach any output.

| Command | Does |
|---|---|
| `atlas.py scan <root>` | tree-sitter scan + framework adapters + clustering → `.atlas/scan.json` (cached per file hash) |
| `atlas.py excerpt <path> <start> <end>` | redacted, line-numbered source for drafting |
| `atlas.py validate <draft>` | rejects any claim that cites code the scan didn't find, unmerged branches, jargon, leaks |
| `atlas.py merge <draft> [--approve]` | folds in your locked corrections; prints the checkpoint outline |
| `atlas.py outline` / `stale` | the outline to review; what changed since you approved |
| `atlas.py render [--format lal,excalidraw,html]` | `.atlas/out/` diagrams |
| `atlas.py walkthrough-context <file>` / `check-walkthrough <md>` | on-demand step-by-step walkthrough of one file |

## Develop

```sh
uv run pytest
```

## License

MIT, see [LICENSE](LICENSE). Third-party notices in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
