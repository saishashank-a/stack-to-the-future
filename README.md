# Stack to the Future

> *Where we're going, we don't need docs.*

A Claude Code skill that scans any codebase, from an enterprise monolith to a student's final-year project, and produces an **anatomy atlas** of it.

The atlas is one business-level workflow diagram per module. The code appears only as labels on each stage, like labelled bones on an anatomy chart:

- **Level 1, Anatomy:** plain-language workflow diagrams a non-technical reader can follow, with a full-body overview linking into each module's plate.
- **Level 2, Function:** a card for every file: its role, the stages it serves, what it receives and hands off, and what breaks if it's gone.
- **Foundation layer:** plumbing (config, DB setup, imports, secrets loading) shown faded underneath.
- **Incomplete code:** stubs and TODOs drawn dotted.

Status: milestone (b) of 7. The static scanner works; naming stages, file cards and diagrams come next. See [PLAN.md](PLAN.md).

## Try the sample

[`examples/leave-desk.atlas.json`](examples/leave-desk.atlas.json) is a hand-written atlas of [`fixtures/leave-desk`](fixtures/leave-desk), a small time-off app built for testing. It shows three approval routes branching and merging on one diagram, two modules, shared systems, the foundation layer and three flags for unfinished code.

```sh
uv run pytest                                                          # all checks
uv run --script skills/stack-to-the-future/scripts/atlas.py scan fixtures/leave-desk   # writes fixtures/leave-desk/.atlas/scan.json
```

## Install (once it does something)

```
/plugin marketplace add saishashank-a/stack-to-the-future
/plugin install stack-to-the-future
```

Requires [uv](https://docs.astral.sh/uv/).

## License

MIT, see [LICENSE](LICENSE). Third-party notices in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
