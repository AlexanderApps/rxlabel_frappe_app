"""The branch's clients and their saved labels. A client belongs to one
branch; another branch's clients are "not found"."""

from __future__ import annotations

import frappe
from rxlabel_core import queue_rules
from rxlabel_core.errors import AppError, unique_message

from .. import branches, checks, licensing, printqueue, session
from ..checks import number, stamp
from .base import command

CLIENT = "RxLabel Client"
CLIENT_LABEL = "RxLabel Client Label"
CLIENT_FIELDS = ["name", "client_name", "contact", "email", "home_address", "creation"]
LABEL_FIELDS = ["name", "client", "product", "instructions", "warning"]


def _branch() -> str:
    return branches.current(session.require()["id"])


def _client(r) -> dict:
    return {"id": r.name, "name": r.client_name, "contact": r.contact, "email": r.email,
            "home_address": r.home_address, "created_at": stamp(r.creation)}


def _label(r) -> dict:
    return {"id": r.name, "client_id": number(r.client), "product": r.product, "instructions": r.instructions,
            "warning": r.warning}


def _own_client(branch: str, client_id) -> int:
    """`client_id` if it is a client of `branch`, else NOT_FOUND."""
    cid = checks.ident(client_id)
    if not frappe.db.exists(CLIENT, {"name": cid, "branch": branch}):
        raise AppError("NOT_FOUND", "Not found")
    return cid


def _own_label(branch: str, label_id) -> int:
    lid = checks.ident(label_id)
    client = frappe.db.get_value(CLIENT_LABEL, lid, "client")
    if client is None or not frappe.db.exists(CLIENT, {"name": client, "branch": branch}):
        raise AppError("NOT_FOUND", "Not found")
    return lid


def _details(name, contact, email, home_address) -> dict:
    return {"client_name": checks.text(name, "Name", required=True), "contact": checks.text(contact, "Contact"),
            "email": checks.text(email, "Email"), "home_address": checks.long_text(home_address, "Home address")}


def _unique(branch: str, name: str, other_than: int | None = None) -> None:
    filters = {"branch": branch, "client_name": name}
    if other_than is not None:
        filters["name"] = ["!=", other_than]
    if frappe.db.exists(CLIENT, filters):
        raise AppError("CONFLICT", unique_message("clients.name"))


def _label_fields(product, instructions, warning) -> dict:
    return {"product": checks.text(product, "Product", required=True),
            "instructions": checks.long_text(instructions, "Instructions"),
            "warning": checks.long_text(warning, "Warning")}


# --- clients ------------------------------------------------------------------------------

@command
def get_clients() -> list[dict]:
    rows = frappe.get_all(CLIENT, filters={"branch": _branch()}, fields=CLIENT_FIELDS,
                          order_by="creation desc, name desc")
    return [_client(r) for r in rows]


@command
def get_client_by_id(id: int) -> dict:
    branch = _branch()
    return _client(frappe.db.get_value(CLIENT, _own_client(branch, id), CLIENT_FIELDS, as_dict=True))


@command
def add_client(name: str, contact: str, email: str, home_address: str | None = None) -> int:
    branch = _branch()
    licensing.require_active()
    values = _details(name, contact, email, home_address)
    _unique(branch, values["client_name"])
    return frappe.get_doc({"doctype": CLIENT, "branch": branch, **values}).insert(ignore_permissions=True).name


@command
def update_client(id: int, name: str, contact: str, email: str, home_address: str | None = None) -> None:
    branch = _branch()
    licensing.require_active()
    cid = _own_client(branch, id)
    values = _details(name, contact, email, home_address)
    _unique(branch, values["client_name"], other_than=cid)
    frappe.db.set_value(CLIENT, cid, values)


@command
def delete_client(id: int) -> None:
    """Also deletes the client's saved labels; queue items keep the name but lose the link."""
    branch = _branch()
    licensing.require_active()
    cid = _own_client(branch, id)
    frappe.db.delete(CLIENT_LABEL, {"client": cid})
    for name in frappe.get_all(printqueue.QUEUE, filters={"client_id": cid}, pluck="name"):
        frappe.db.set_value(printqueue.QUEUE, name, "client_id", None, update_modified=False)
    frappe.delete_doc(CLIENT, cid, ignore_permissions=True)


@command
def count_clients() -> int:
    return frappe.db.count(CLIENT, {"branch": _branch()})


# --- their labels ---------------------------------------------------------------------------

@command
def get_client_labels(client_id: int) -> list[dict]:
    branch = _branch()
    cid = checks.ident(client_id)
    if not frappe.db.exists(CLIENT, {"name": cid, "branch": branch}):
        return []
    return [_label(r) for r in frappe.get_all(CLIENT_LABEL, filters={"client": cid}, fields=LABEL_FIELDS,
                                              order_by="name asc")]


@command
def add_client_label(client_id: int, product: str, instructions: str | None = None,
                     warning: str | None = None) -> int:
    branch = _branch()
    licensing.require_active()
    cid = _own_client(branch, client_id)
    values = _label_fields(product, instructions, warning)
    return frappe.get_doc({"doctype": CLIENT_LABEL, "client": cid, **values}).insert(ignore_permissions=True).name


@command
def add_client_labels(data: list[dict]) -> None:
    """Several labels, all or none."""
    branch = _branch()
    licensing.require_active()
    items = []
    for d in data if isinstance(data, list) else []:
        if not isinstance(d, dict) or not isinstance(d.get("client_id"), int) or not isinstance(d.get("product"), str):
            raise AppError("VALIDATION", "Each label needs a client and a product.")
        items.append({"client": _own_client(branch, d["client_id"]),
                      **_label_fields(d["product"], d.get("instructions"), d.get("warning"))})
    for item in items:
        frappe.get_doc({"doctype": CLIENT_LABEL, **item}).insert(ignore_permissions=True)


@command
def update_client_label(id: int, product: str, instructions: str | None = None, warning: str | None = None) -> None:
    branch = _branch()
    licensing.require_active()
    frappe.db.set_value(CLIENT_LABEL, _own_label(branch, id), _label_fields(product, instructions, warning))


@command
def delete_client_label(id: int) -> None:
    branch = _branch()
    licensing.require_active()
    frappe.db.delete(CLIENT_LABEL, {"name": _own_label(branch, id)})


@command
def count_client_labels(client_id: int) -> int:
    branch = _branch()
    cid = checks.ident(client_id)
    if not frappe.db.exists(CLIENT, {"name": cid, "branch": branch}):
        return 0
    return frappe.db.count(CLIENT_LABEL, {"client": cid})


@command
def copy_client_label_to_queue(id: int, make_room: bool | None = False) -> None:
    """Copy all of client `id`'s saved labels to the queue. QUEUE_FULL unless
    `make_room` when the oldest would be dropped."""
    branch = _branch()
    licensing.require_active()
    cid = _own_client(branch, id)
    labels = frappe.get_all(CLIENT_LABEL, filters={"client": cid}, fields=LABEL_FIELDS, order_by="name asc")
    limit = printqueue.limit(branch)
    queue_rules.check_room(printqueue.count(branch), len(labels), limit, checks.flag(make_room))
    name = frappe.db.get_value(CLIENT, cid, "client_name")
    for r in labels:
        printqueue.add(branch, r.product, r.instructions, r.warning, name, client_id=cid)
    printqueue.trim(branch, limit)
