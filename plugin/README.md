# Stack to the Future

> *Where we're going, we don't need docs.*

A Claude Code plugin that scans any codebase and draws an **anatomy atlas** of it: one plain-language business workflow diagram per module, with the source files as labels on each stage. Every file gets a card describing its role and what it hands off. Plumbing such as config and database setup is drawn faded underneath, and unfinished code is drawn dotted. A validator rejects any claim that cites code the scan didn't find, and you approve the outline before anything is rendered. Output is offline HTML, Excalidraw and `.lal`.

## Install

```
claude plugin marketplace add saishashank-a/stack-to-the-future
claude plugin install stack-to-the-future@stack-to-the-future
```

Requires [uv](https://docs.astral.sh/uv/). Then ask Claude to "map this codebase" or run `/stack-to-the-future`.

## Privacy

Everything runs on your machine. The scripts read the repository you point them at and write the scan, drafts and diagrams to `<repo>/.atlas/`. Nothing is sent to the plugin author or any third party, and there is no telemetry or server. Source excerpts the scripts hand to Claude have secret values (API keys, passwords, tokens, `.env` contents) redacted, and the validator rejects any atlas that would show one. The only network use is `uv` downloading the Python packages the scripts declare. Your conversation with Claude is covered by Anthropic's own privacy policy.

## Source and license

Source, sample atlas and docs: https://github.com/saishashank-a/stack-to-the-future. MIT, see [LICENSE](LICENSE).
