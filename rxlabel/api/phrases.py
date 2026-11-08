"""The instruction builder: saved phrases and options (company-wide), and
common instructions (the label library and this branch's client labels)."""

from __future__ import annotations

from collections import Counter

import frappe
from rxlabel_core import access
from rxlabel_core import phrases as rules

from .. import branches, licensing, prefs, session
from .base import command


@command
def get_instruction_phrases() -> list[str]:
    me = session.require()
    return prefs.get(rules.PHRASES_KEY, branches.current(me["id"])) or list(rules.STARTER_PHRASES)


@command
def save_instruction_phrases(phrases: list[str]) -> list[str]:
    me = session.require(access.STAFF)
    licensing.require_active()
    cleaned = rules.clean_phrases(phrases)
    prefs.set_(rules.PHRASES_KEY, cleaned, branches.current(me["id"]))
    return cleaned


@command
def get_instruction_options() -> dict | None:
    me = session.require()
    return prefs.get(rules.OPTIONS_KEY, branches.current(me["id"]))


@command
def save_instruction_options(options: dict | None = None) -> dict | None:
    me = session.require(access.STAFF)
    licensing.require_active()
    cleaned = rules.clean_option_lists(options) if options is not None else None
    prefs.set_(rules.OPTIONS_KEY, cleaned, branches.current(me["id"]))
    return cleaned


def _counted(texts, limit: int) -> list[tuple[str, int]]:
    # As the standalone app's SQL: TRIM (spaces only), skip empty, most used first, then A-Z.
    counts = Counter(t.strip(" ") for t in texts if t is not None and t.strip(" "))
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


@command
def get_common_instructions() -> list[dict]:
    me = session.require()
    branch = branches.current(me["id"])
    n = rules.COMMON_INSTRUCTIONS_LIMIT
    clients = frappe.get_all("RxLabel Client", filters={"branch": branch}, pluck="name")
    own = (frappe.get_all("RxLabel Client Label", filters={"client": ["in", clients]}, pluck="instructions")
           if clients else [])
    own += frappe.get_all("RxLabel Label", filters={"is_custom": 1}, pluck="instructions")
    preloaded = frappe.get_all("RxLabel Label", filters={"is_custom": 0}, pluck="instructions")
    return rules.merge_common(_counted(own, n), _counted(preloaded, n))
