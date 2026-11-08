"""The branch's print queue (RxLabel Queue Item)."""

from __future__ import annotations

import frappe
from rxlabel_core import queue_rules

from . import prefs
from .checks import number, stamp

QUEUE = "RxLabel Queue Item"
CLIENT = "RxLabel Client"
FIELDS = ["name", "product", "instructions", "warning", "client", "creation", "client_id"]


def limit(branch: str) -> int:
    size = frappe.db.get_value(prefs.BRANCH_SETTINGS, branch, "queue_size")
    return max(1, int(size or 0) or queue_rules.DEFAULT_QUEUE_SIZE)


def count(branch: str) -> int:
    return frappe.db.count(QUEUE, {"branch": branch})


def items(branch: str) -> list[dict]:
    rows = frappe.get_all(QUEUE, filters={"branch": branch}, fields=FIELDS, order_by="creation asc, name asc")
    return [{"id": r.name, "product": r.product, "instructions": r.instructions, "warning": r.warning,
             "client": r.client, "created_at": stamp(r.creation), "client_id": number(r.client_id)} for r in rows]


def add(branch: str, product: str, instructions, warning, client, client_id=None) -> None:
    if client_id is None and client:
        client_id = frappe.db.get_value(CLIENT, {"branch": branch, "client_name": client}, "name")
    frappe.get_doc({"doctype": QUEUE, "branch": branch, "product": product, "instructions": instructions,
                    "warning": warning, "client": client, "client_id": client_id}).insert(ignore_permissions=True)


def remove(branch: str, ids: list[int]) -> None:
    for i in ids:
        frappe.db.delete(QUEUE, {"name": i, "branch": branch})


def clear(branch: str) -> None:
    frappe.db.delete(QUEUE, {"branch": branch})


def purge_older_than(branch: str, days: int) -> None:
    if days > 0:
        cutoff = frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-days)
        frappe.db.delete(QUEUE, {"branch": branch, "creation": ["<", cutoff]})


def trim(branch: str, keep: int) -> None:
    """Delete the oldest items beyond `keep`."""
    names = frappe.get_all(QUEUE, filters={"branch": branch}, pluck="name", order_by="creation asc, name asc")
    for name in names[: max(0, len(names) - max(1, keep))]:
        frappe.db.delete(QUEUE, {"name": name})
