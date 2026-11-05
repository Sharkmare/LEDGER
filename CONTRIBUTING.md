# Contributing

## Setup

LEDGER has no dependencies. It needs Python 3.10 or newer, and Node only if you want the page renderer tests to run.

```bash
python -m ledger.server
python -m unittest discover -s tests
git config core.hooksPath .githooks
```

The last line turns on the commit message check described below.

## Commit messages

Keep them short. The history should read like a changelog when you run `git log --oneline`.

```
<what changed, in plain words>
```

- One commit per change. Squash fixups, review tweaks and "fix typo" commits into the commit they belong to before you merge.
- A single line, 72 characters or fewer. It names the change, not the files and not the steps. Plain sentence, no prefix needed, no full stop needed.
- No body. Add one only when a reader could not guess why: at most five short lines, a blank line after the first line, nothing the diff already shows. Anything longer belongs in the pull request or the docs.
- Point at an issue at the end of the line, `Fix list limit parsing (#12)`, or close it with `Closes #12` on its own line.
- No merge commits. Rebase your branch on main and squash it.
- Use a comma, a colon or two sentences instead of a long dash.

| Good | Not good |
|---|---|
| `Add a knowledge base with a Tools category` | `Update` |
| `Stop the board refresh from closing the editor` | `Fix bug in ledger.js where the poll replaced main while an editor draft was open and it broke` |
| `Fix list limit parsing (#12)` | `fixup! Fix list limit parsing` |
| `Refuse tickets with a due date before the start date` | `Changes to store.py, server.py and tests` |

`tools/check_commit_message.py` enforces the mechanical parts (length, an empty or vague subject, a long body, merge and fixup commits, long dashes). The hook in `.githooks` runs it on every commit once `core.hooksPath` is set.

## Code

- Standard library only. A new dependency needs a reason that a small piece of code cannot meet.
- No comments or docstrings. Names carry the meaning. A rule or a trap goes in the docs or in a test.
- Every behaviour has a test, and the test must be able to fail. Prove it by breaking the code and watching the test catch it.
- Every API route is described in `ledger/openapi.py`; a test fails when one is missing.
- Docs change in the same commit as the behaviour they describe.
- Write plainly in docs and in the interface.

## Before you push

```bash
python -m unittest discover -s tests
```
