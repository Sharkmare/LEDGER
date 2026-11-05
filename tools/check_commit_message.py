from __future__ import annotations

import sys
from pathlib import Path

SUBJECT_LIMIT = 72
BODY_LINES_LIMIT = 5
BODY_WIDTH_LIMIT = 100
VAGUE_SUBJECTS = {"update", "updates", "fix", "fixes", "change", "changes", "wip", "misc", "stuff", "commit", "tweaks", "cleanup", "more"}
DASHES = (chr(0x2014), chr(0x2013))


def message_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if not line.startswith("#")]


def problems(text: str) -> list[str]:
    lines = message_lines(text)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ["the message is empty; write one line saying what changed"]
    found = []
    subject, rest = lines[0], lines[1:]
    if len(subject) > SUBJECT_LIMIT:
        found.append(f"the first line is {len(subject)} characters; keep it to {SUBJECT_LIMIT} or fewer")
    if subject.strip().lower().rstrip(".") in VAGUE_SUBJECTS:
        found.append(f"{subject.strip()!r} says nothing; name what changed")
    if subject.startswith(("Merge ", "Revert \"Merge")):
        found.append("do not make merge commits; rebase the branch and squash it to one commit")
    if subject.startswith(("fixup!", "squash!")):
        found.append("squash fixup commits into the commit they fix before committing")
    if rest and rest[0].strip():
        found.append("leave the second line empty when there is more than one line")
    body = [line for line in rest if line.strip()]
    if len(body) > BODY_LINES_LIMIT:
        found.append(f"the body is {len(body)} lines; more than {BODY_LINES_LIMIT} belongs in the pull request or the docs")
    for line in body:
        if len(line) > BODY_WIDTH_LIMIT:
            found.append(f"a body line is {len(line)} characters; keep lines to {BODY_WIDTH_LIMIT} or fewer")
            break
    if any(dash in text for dash in DASHES):
        found.append("use a comma, a colon or two sentences instead of a long dash")
    return found


def main(arguments: list[str]) -> int:
    if len(arguments) != 1:
        print("usage: check_commit_message.py MESSAGE_FILE", file=sys.stderr)
        return 2
    found = problems(Path(arguments[0]).read_text(encoding="utf-8"))
    for problem in found:
        print(f"commit message: {problem}", file=sys.stderr)
    if found:
        print("See CONTRIBUTING.md, section Commit messages.", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
