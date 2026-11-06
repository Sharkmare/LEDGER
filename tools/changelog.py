from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "CHANGELOG.md"
TAG_PATTERN = "v*"
RELEASE_COMMIT = re.compile(r"^LEDGER v\d+\.\d+\.\d+$")
SECTION_ORDER = ("Added", "Changed", "Fixed", "Removed")
ADDED_VERBS = {"add", "show", "support", "introduce", "allow"}
FIXED_VERBS = {"fix", "stop", "refuse", "keep", "prevent", "handle"}
REMOVED_VERBS = {"remove", "drop"}
HEADER = (
    "# Changelog\n\n"
    "Generated from commit subjects by `tools/changelog.py` when a release is cut. Do not edit it by hand: "
    "a subject's first word picks its heading (see CONTRIBUTING.md).\n"
)


def run_git(arguments: list[str], repository: Path) -> str:
    result = subprocess.run(["git", *arguments], cwd=repository, capture_output=True, text=True, encoding="utf-8", check=True)
    return result.stdout.strip()


def heading_for(subject: str) -> str:
    verb = subject.split(" ", 1)[0].lower()
    if verb in ADDED_VERBS:
        return "Added"
    if verb in FIXED_VERBS:
        return "Fixed"
    if verb in REMOVED_VERBS:
        return "Removed"
    return "Changed"


def read_commits(repository: Path, revision_range: str) -> list[tuple[str, str]]:
    output = run_git(["log", "--reverse", "--format=%h%x1f%s", revision_range], repository)
    commits = [tuple(line.split("\x1f", 1)) for line in output.splitlines() if line]
    return [(short, subject) for short, subject in commits if not RELEASE_COMMIT.match(subject)]


def tag_versions(repository: Path) -> list[str]:
    return run_git(["tag", "--list", TAG_PATTERN, "--sort=v:refname"], repository).splitlines()


def tag_date(repository: Path, tag: str) -> str:
    return run_git(["log", "-1", "--format=%ad", "--date=short", tag], repository)


def release_sections(repository: Path, upcoming: str | None, today: str) -> list[dict]:
    tags = tag_versions(repository)
    sections = []
    for index, tag in enumerate(tags):
        revision_range = f"{tags[index - 1]}..{tag}" if index else tag
        sections.append({"title": tag.removeprefix("v"), "date": tag_date(repository, tag), "commits": read_commits(repository, revision_range)})
    pending = read_commits(repository, f"{tags[-1]}..HEAD" if tags else "HEAD")
    if upcoming and f"v{upcoming}" in tags:
        raise ValueError(f"version {upcoming} is already tagged")
    if upcoming:
        sections.append({"title": upcoming, "date": today, "commits": pending})
    elif pending:
        sections.append({"title": "Unreleased", "date": "", "commits": pending})
    return list(reversed(sections))


def render_section(section: dict) -> str:
    title = f"## {section['title']} ({section['date']})" if section["date"] else f"## {section['title']}"
    grouped = {name: [] for name in SECTION_ORDER}
    for short, subject in section["commits"]:
        grouped[heading_for(subject)].append(f"- {subject} (`{short}`)")
    blocks = [f"### {name}\n\n" + "\n".join(lines) for name, lines in grouped.items() if lines]
    return title + "\n\n" + ("\n\n".join(blocks) if blocks else "No changes recorded.") + "\n"


def render(sections: list[dict]) -> str:
    return HEADER + "\n" + "\n".join(render_section(section) for section in sections)


def generate(repository: Path, upcoming: str | None = None, today: str | None = None) -> str:
    return render(release_sections(repository, upcoming, today or datetime.date.today().isoformat()))


def main(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate CHANGELOG.md from commit subjects between version tags.")
    parser.add_argument("--release", metavar="X.Y.Z", help="the version being cut; commits since the last tag are listed under it")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true", help="exit 1 when the file differs from what would be generated")
    options = parser.parse_args(arguments)
    if options.release and not re.fullmatch(r"\d+\.\d+\.\d+", options.release):
        parser.error("--release takes a version such as 1.2.0")
    text = generate(options.repository, options.release)
    if options.check:
        current = options.output.read_text(encoding="utf-8") if options.output.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"{options.output.name} is out of date; run tools/changelog.py", file=sys.stderr)
            return 1
        return 0
    options.output.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {options.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
