# Stack to the Future

> *Where we're going, we don't need docs.*

A Claude Code skill that scans any codebase, from an enterprise monolith to a student's final-year project, and produces an **anatomy atlas** of it.

The atlas is one business-level workflow diagram per module. The code appears only as labels on each stage, like labelled bones on an anatomy chart:

- **Level 1, Anatomy:** plain-language workflow diagrams a non-technical reader can follow, with a full-body overview linking into each module's plate.
- **Level 2, Function:** a card for every file: its role, the stages it serves, what it receives and hands off, and what breaks if it's gone.
- **Foundation layer:** plumbing (config, DB setup, imports, secrets loading) shown faded underneath.
- **Incomplete code:** stubs and TODOs drawn dotted.

Status: planning. See [PLAN.md](PLAN.md).

## License

MIT, see [LICENSE](LICENSE). Third-party notices in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
