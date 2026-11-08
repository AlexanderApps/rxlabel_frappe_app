"""Label search by product name (src-tauri/src/label_search.rs).

Each label is ranked by the first method that matches it, then A-Z:
1. starts with, 2. contains, 3. all words in any order (each typed word
starts a word of the name), 4. typing mistakes (fewest first). With
patterns on, a query between slashes is a case-insensitive regex.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import AppError

LIMIT = 60
MAX_PATTERN_CHARS = 200
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class SearchOptions:
    all_words: bool = True
    fuzzy: bool = False
    patterns: bool = False


def words_of(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _pattern_of(query: str) -> str | None:
    if len(query) >= 2 and query.startswith("/") and query.endswith("/"):
        return query[1:-1]
    return None


def _distance(a: str, b: str, cap: int) -> int:
    """Levenshtein distance, stopping early once it exceeds `cap`."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def _allowed_mistakes(word: str) -> int:
    return 0 if len(word) < 4 else 1 if len(word) <= 7 else 2


def _word_mistakes(q: str, name_words: list[str]) -> int | None:
    """Fewest mistakes for one typed word against a name's words (None: no match)."""
    best = None
    allowed = _allowed_mistakes(q)
    for w in name_words:
        if w.startswith(q):
            return 0
        if allowed and w[:1] == q[:1]:
            # Compare with the word's start of the same length too (typing in progress).
            d = min(_distance(q, w, allowed), _distance(q, w[: len(q)], allowed))
            if d <= allowed and (best is None or d < best):
                best = d
    return best


def search(entries: list[tuple[int, str]], query: str, options: SearchOptions, limit: int = LIMIT) -> list[int]:
    """`entries` = (id, product) sorted A-Z. Returns matching ids, best first."""
    trimmed = query.strip()
    if options.patterns and (pattern := _pattern_of(trimmed)) is not None:
        if len(pattern) > MAX_PATTERN_CHARS:
            raise AppError("INVALID_PATTERN", f"Patterns can be at most {MAX_PATTERN_CHARS} characters.")
        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error:
            raise AppError("INVALID_PATTERN", "Invalid pattern") from None
        return [i for i, p in entries if rx.search(p)][:limit]

    q = trimmed.lower()
    if not q:
        return [i for i, _ in entries[:limit]]

    lowered = [(i, p.lower()) for i, p in entries]
    starts = [i for i, p in lowered if p.startswith(q)]
    contains = [i for i, p in lowered if not p.startswith(q) and q in p]
    ranked = (starts + contains)[:limit]
    seen = set(ranked)

    qwords = words_of(q)
    if len(ranked) < limit and qwords and options.all_words:
        for i, p in lowered:
            if i in seen:
                continue
            name_words = words_of(p)
            if all(any(w.startswith(qw) for w in name_words) for qw in qwords):
                ranked.append(i)
                seen.add(i)
                if len(ranked) >= limit:
                    return ranked

    if len(ranked) < limit and qwords and options.fuzzy:
        scored = []
        for i, p in lowered:
            if i in seen:
                continue
            name_words = words_of(p)
            total = 0
            for qw in qwords:
                m = _word_mistakes(qw, name_words)
                if m is None:
                    break
                total += m
            else:
                if total > 0:
                    scored.append((total, i))
        scored.sort(key=lambda t: t[0])  # stable: keeps A-Z within the same count
        ranked.extend(i for _, i in scored[: limit - len(ranked)])
    return ranked
