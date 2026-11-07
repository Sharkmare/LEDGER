from __future__ import annotations

import re
import sqlite3
from difflib import SequenceMatcher

from . import store

MIN_SCORE = 0.55
DEFAULT_LIMIT = 3
MAX_RATIO_CANDIDATES = 150
MAX_LIMIT = 10
STOP_WORDS = frozenset(
    "a an and are as at be but by for from has have in into is it its of on or that the this to was were will with".split())
WORD_PATTERN = re.compile(r"[a-z0-9]+")


def normalise(title: str) -> str:
    return " ".join(WORD_PATTERN.findall(str(title).lower()))


def significant_words(title: str) -> frozenset:
    return frozenset(word for word in WORD_PATTERN.findall(str(title).lower()) if word not in STOP_WORDS)


def overlap_of(query_words: frozenset, candidate_words: frozenset) -> float:
    return len(query_words & candidate_words) / len(query_words | candidate_words)


def find(connection: sqlite3.Connection, project_key: str, title: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    query_text = normalise(title)
    query_words = significant_words(title)
    if not query_words:
        return []
    key_prefix = str(project_key).upper()
    closed = ",".join("?" for _ in store.CLOSED_STATUSES)
    rows = connection.execute(
        f"SELECT number, title, status FROM tickets WHERE project_key = ? AND status NOT IN ({closed})",
        (key_prefix, *store.CLOSED_STATUSES)).fetchall()
    sharing = []
    for row in rows:
        candidate_words = significant_words(row["title"])
        if not query_words.isdisjoint(candidate_words):
            sharing.append((overlap_of(query_words, candidate_words), row))
    sharing.sort(key=lambda pair: (-pair[0], pair[1]["number"]))
    matcher = SequenceMatcher(None, "", query_text, autojunk=False)
    matches = []
    for overlap, row in sharing[:MAX_RATIO_CANDIDATES]:
        value = 1.0 if overlap >= 1.0 else max(overlap, text_ratio(matcher, normalise(row["title"]), overlap))
        if value >= MIN_SCORE:
            matches.append({"key": f"{key_prefix}-{row['number']}", "title": row["title"], "status": row["status"],
                            "score": round(value, 3), "number": row["number"]})
    matches.sort(key=lambda match: (-match["score"], match["number"]))
    return [{name: match[name] for name in ("key", "title", "status", "score")} for match in matches[:limit]]


def text_ratio(matcher: SequenceMatcher, candidate_text: str, overlap: float) -> float:
    matcher.set_seq1(candidate_text)
    if overlap < MIN_SCORE and (matcher.real_quick_ratio() < MIN_SCORE or matcher.quick_ratio() < MIN_SCORE):
        return 0.0
    return matcher.ratio()
