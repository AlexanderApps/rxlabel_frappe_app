"""Instruction builder lists (commands/phrases.rs): saved phrases and the
options for each part of a dose."""

from __future__ import annotations

from .errors import AppError

PHRASES_KEY = "instruction_phrases"
OPTIONS_KEY = "instruction_options"
MAX_PHRASES, MAX_PHRASE_CHARS = 50, 300
MAX_OPTIONS, MAX_OPTION_CHARS = 40, 80
OPTION_KINDS = ("action", "count", "form", "amount", "water", "site", "frequency", "timing", "duration", "interval")
STARTER_PHRASES = (
    "Take with food to reduce stomach upset",
    "Take on an empty stomach",
    "Shake well before use",
    "Complete the full course",
)
COMMON_INSTRUCTIONS_LIMIT = 20


def _tidy(text: object) -> str:
    return " ".join(str(text).split())


def clean_phrases(phrases: list) -> list[str]:
    """Trimmed, without blanks or repeats; refused when too long or too many."""
    out: list[str] = []
    for p in map(_tidy, phrases):
        if not p or any(o.lower() == p.lower() for o in out):
            continue
        if len(p) > MAX_PHRASE_CHARS:
            raise AppError("VALIDATION", f"A phrase can be at most {MAX_PHRASE_CHARS} characters.")
        out.append(p)
    if len(out) > MAX_PHRASES:
        raise AppError("VALIDATION", f"Keep at most {MAX_PHRASES} saved phrases.")
    return out


def clean_option_lists(lists: dict) -> dict[str, list[str]]:
    """Every list tidied; unknown parts refused."""
    result = {}
    for kind in sorted(lists):
        if kind not in OPTION_KINDS:
            raise AppError("VALIDATION", f'Unknown part "{kind}".')
        out: list[str] = []
        for o in map(_tidy, lists[kind]):
            if not o or o in out:
                continue
            if len(o) > MAX_OPTION_CHARS:
                raise AppError("VALIDATION", f"An option can be at most {MAX_OPTION_CHARS} characters.")
            out.append(o)
        if not out:
            raise AppError("VALIDATION", f'Keep at least one option for "{kind}".')
        if len(out) > MAX_OPTIONS:
            raise AppError("VALIDATION", f"Keep at most {MAX_OPTIONS} options for each part.")
        result[kind] = out
    return result


def merge_common(own: list[tuple[str, int]], preloaded: list[tuple[str, int]],
                 limit: int = COMMON_INSTRUCTIONS_LIMIT) -> list[dict]:
    """The pharmacy's own instructions first, then common preloaded ones (common_instructions)."""
    out = [{"text": t, "uses": n, "own": True} for t, n in own[:limit]]
    seen = {o["text"] for o in out}
    for t, n in preloaded:
        if len(out) >= limit:
            break
        if t not in seen:
            out.append({"text": t, "uses": n, "own": False})
    return out
