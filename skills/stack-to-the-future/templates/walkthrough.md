# Walkthrough format

Write `<root>/.atlas/walkthroughs/<path>.md` (e.g. `.atlas/walkthroughs/app/leave/service.py.md`) from the output of `atlas.py walkthrough-context <path>`. The reader is new to the codebase and may not be a programmer.

## Rules

- **Plain language in prose.** Say what happens in business terms ("the request is marked approved"), not in code terms. Any code identifier, file name or value goes inside backticks.
- **Cite every claim.** A citation is a backticked `path:start-end`, optionally followed by a space and the symbol: `` `app/leave/service.py:13-19 choose_route` ``. A single line is `` `path:42` ``. Cite only lines shown in the context's source; the symbol must be one listed under "Symbols" and its lines must overlap the cited range.
- **Reading order.** Steps follow the file from top to bottom, one step per meaningful block (usually one function or one branch). Skip imports unless they say something about the design.
- **Every step cites at least one range.** `atlas.py check-walkthrough` rejects a step without one.
- **No secret values.** The source you see is already redacted; never reconstruct or guess what was redacted.
- **Use the card.** "What this file is for", "Where it hands off" and "What breaks if it's gone" start from the card and stages in the context; correct them only if the source clearly says otherwise, and say so.

## Shape

```markdown
# <path>

## What this file is for

<one or two sentences from the card's role, plus which stages of which workflow it serves>

## Step by step

### 1. <what happens, in business words>

<two to four sentences: what this part decides or does, and why it matters to the people in the workflow>

`<path>:<start>-<end> <symbol>`

### 2. <next thing that happens>

...

## Where it hands off

- <what it passes on, in plain words> → <who receives it> `<path>:<start>-<end> <symbol>`

## What breaks if it's gone

<from the card's if_removed, in plain words>

## Open issues

- <each flag, TODO, stub or missing step that touches this file, with its citation; "None found." if there are none>
```
