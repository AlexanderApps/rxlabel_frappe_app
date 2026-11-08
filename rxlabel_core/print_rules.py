"""Printing rules (commands/print.rs, commands/print_check.rs): what the
history keeps, each label's outcome, and the warnings before printing."""

from __future__ import annotations

from typing import Any, Callable, Mapping

KEEP_DAYS = 30
MAX_HISTORY_ROWS = 5000
# A batch the browser never reported (tab closed mid-print) is recorded as
# "did not print" after this long, so nothing disappears silently.
UNREPORTED_AFTER_MINUTES = 30
UNREPORTED_CODE = "no_result"


def as_vars(values: Mapping[str, Any]) -> dict[str, str]:
    """Settings or a label as template values: text, missing = empty (to_vars)."""
    return {k: "" if v is None else str(v) for k, v in values.items()}


def merge_globals(labels: list[Any], globals_: Mapping[str, str]) -> list[dict]:
    """Facility settings and the user's name override same-named label fields (enqueue_print)."""
    return [{**(v if isinstance(v, dict) else {}), **globals_} for v in labels]


def _field(values: Mapping[str, Any], key: str) -> str | None:
    v = str(values.get(key) or "").strip()
    return v or None


def history_rows(user: Mapping[str, Any], template: str, labels: list[Mapping[str, Any]],
                 copies: list[int]) -> list[dict]:
    """What the history keeps about each label (history_rows)."""
    return [
        {"user_id": user["id"], "user_name": user["name"], "product": _field(v, "product") or "",
         "client": _field(v, "client"), "template": template, "copies": n}
        for v, n in zip(labels, copies)
    ]


def with_outcomes(rows: list[dict], owner: list[int], results: list[Mapping[str, Any]]) -> list[dict]:
    """Each label's outcome from its copies' results: printed only when every copy
    printed; held when any copy went to a printer that wasn't connected; else
    failed, with the first error code (with_outcomes)."""
    done = [0] * len(rows)
    held = [False] * len(rows)
    error: list[str | None] = [None] * len(rows)
    for r in results:
        index = r.get("index")
        if not isinstance(index, int) or not 0 <= index < len(owner):
            continue
        label = owner[index]
        if r.get("success"):
            done[label] += 1
            held[label] |= bool(r.get("held"))
        elif error[label] is None:
            error[label] = str(r.get("code") or "print_failed")
    out = []
    for i, row in enumerate(rows):
        if error[i] is not None:
            outcome, code = "failed", error[i]
        elif done[i] >= row["copies"]:
            outcome, code = ("held" if held[i] else "printed"), None
        else:
            outcome, code = "failed", None
        out.append({**row, "outcome": outcome, "error_code": code})
    return out


def unreported(rows: list[dict]) -> list[dict]:
    return [{**row, "outcome": "failed", "error_code": UNREPORTED_CODE} for row in rows]


def _ago(minutes: int) -> str:
    if minutes == 0:
        return "less than a minute ago"
    return "1 minute ago" if minutes == 1 else f"{minutes} minutes ago"


_FIELD_PHRASE = {"product": "the product name is", "instructions": "the instructions are",
                 "warning": "the warning is"}


def check_labels(vars_list: list[Any], recent: Callable[[str, str], int | None],
                 too_long: Callable[[dict], list[str]] | None = None) -> list[dict]:
    """Warnings before printing (check_labels): a likely double print (`recent`:
    minutes since this product last went out for this client, or None), a
    duplicate in this batch, no instructions, and text too long to print at a
    readable size (`too_long`: the fields, from label_checks)."""
    warnings, seen = [], set()
    for index, values in enumerate(vars_list if isinstance(vars_list, list) else []):
        values = values if isinstance(values, dict) else {}
        product = str(values.get("product") or "").strip()
        client = str(values.get("client") or "").strip()
        label = product or "A label"
        if client:
            key = (product.lower(), client.lower())
            if key in seen:
                warnings.append({"index": index, "kind": "duplicate_in_batch",
                                 "message": f"{label} for {client} is in this print job more than once."})
            else:
                seen.add(key)
                minutes = recent(product, client)
                if minutes is not None:
                    warnings.append({"index": index, "kind": "recently_printed",
                                     "message": f"{label} was already printed for {client} {_ago(minutes)}."})
        if not str(values.get("instructions") or "").strip():
            warnings.append({"index": index, "kind": "no_instructions", "message": f"{label} has no instructions."})
        for field in (too_long(as_vars(values)) if too_long else []):
            phrase = _FIELD_PHRASE.get(field, "the client name is")
            warnings.append({"index": index, "kind": "too_long",
                             "message": f"{label}: {phrase} too long to print at a readable size. "
                                        "Shorten it, or choose a template with more room."})
    return warnings
