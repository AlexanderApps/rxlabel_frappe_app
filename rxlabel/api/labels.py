"""The label library, shared by the company's branches."""

from __future__ import annotations

import frappe
from rxlabel_core.errors import AppError
from rxlabel_core.label_search import SearchOptions, search

from .. import branches, checks, licensing, prefs, session
from ..checks import stamp
from .base import command

LABEL = "RxLabel Label"
FIELDS = ["name", "product", "instructions", "warning", "is_custom", "creation"]


def _label(r) -> dict:
    return {"id": r.name, "product": r.product, "instructions": r.instructions, "warning": r.warning,
            "is_custom": bool(r.is_custom), "created_at": stamp(r.creation)}


def _options(branch: str) -> SearchOptions:
    d = SearchOptions()
    return SearchOptions(all_words=bool(prefs.get("label_search_all_words", branch, d.all_words)),
                         fuzzy=bool(prefs.get("label_search_fuzzy", branch, d.fuzzy)),
                         patterns=bool(prefs.get("label_search_patterns", branch, d.patterns)))


def _sorted(rows) -> list:
    # A-Z as the standalone app sorts (by character code), not MariaDB's collation.
    return sorted(rows, key=lambda r: (r.product, r.name))


def _fields(product, instructions, warning) -> tuple:
    return (checks.text(product, "Product", required=True), checks.long_text(instructions, "Instructions"),
            checks.long_text(warning, "Warning"))


@command
def get_labels(search_term: str | None = None) -> list[dict]:
    """Labels matching `search_term` by product name, best first (at most 60)."""
    me = session.require()
    names = [(r.name, r.product) for r in _sorted(frappe.get_all(LABEL, fields=["name", "product"]))]
    ids = search(names, search_term or "", _options(branches.current(me["id"])))
    if not ids:
        return []
    found = {r.name: _label(r) for r in frappe.get_all(LABEL, filters={"name": ["in", ids]}, fields=FIELDS)}
    return [found[i] for i in ids if i in found]


@command
def get_all_labels() -> list[dict]:
    session.require()
    return [_label(r) for r in _sorted(frappe.get_all(LABEL, fields=FIELDS))]


@command
def create_label(product: str, instructions: str, warning: str) -> int:
    session.require()
    licensing.require_active()
    product, instructions, warning = _fields(product, instructions, warning)
    doc = frappe.get_doc({"doctype": LABEL, "product": product, "instructions": instructions, "warning": warning,
                          "is_custom": 1}).insert(ignore_permissions=True)
    return doc.name


@command
def update_label(id: int, product: str, instructions: str, warning: str) -> None:
    """Editing a preloaded label's text makes it the pharmacy's own; saving it unchanged doesn't."""
    session.require()
    licensing.require_active()
    label_id = checks.ident(id)
    product, instructions, warning = _fields(product, instructions, warning)
    old = frappe.db.get_value(LABEL, label_id, ["product", "instructions", "warning", "is_custom"], as_dict=True)
    if old is None:
        raise AppError("NOT_FOUND", "That label no longer exists.")
    same = (old.product, old.instructions, old.warning) == (product, instructions, warning)
    frappe.db.set_value(LABEL, label_id, {"product": product, "instructions": instructions, "warning": warning,
                                          "is_custom": old.is_custom if same else 1})


@command
def delete_label(id: int) -> None:
    session.require()
    licensing.require_active()
    frappe.db.delete(LABEL, {"name": checks.ident(id)})
