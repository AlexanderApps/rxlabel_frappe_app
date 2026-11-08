"""Print history and the batches browsers are printing, per branch
(RxLabel Print History, RxLabel Print Batch). Times are kept in the site's
time zone, as Frappe keeps them, and sent to the browser in UTC."""

from __future__ import annotations

import json
import secrets

import frappe
from rxlabel_core import print_rules

from .checks import SHORT, stamp

HISTORY = "RxLabel Print History"
BATCH = "RxLabel Print Batch"


def _ago(minutes: int):
    return frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-minutes)


def record(branch: str, rows: list[dict]) -> None:
    printed_at = frappe.utils.now_datetime()
    for row in rows:
        frappe.get_doc({
            "doctype": HISTORY, "branch": branch, "printed_at": printed_at, "user": row["user_id"],
            "user_name": (row.get("user_name") or "")[:SHORT], "product": (row.get("product") or "")[:SHORT],
            "client": (row.get("client") or None) and row["client"][:SHORT], "template": str(row["template"])[:SHORT],
            "copies": int(row["copies"]), "outcome": row["outcome"], "error_code": row.get("error_code"),
        }).insert(ignore_permissions=True)


def purge(keep_days: int = print_rules.KEEP_DAYS) -> None:
    frappe.db.delete(HISTORY, {"printed_at": ["<", _ago(keep_days * 1440)]})


def recent(branch: str, days: int, max_rows: int) -> dict:
    filters = {"branch": branch, "printed_at": [">=", _ago(days * 1440)]}
    rows = frappe.get_all(HISTORY, filters=filters, order_by="printed_at desc, name desc", limit=max_rows,
                          fields=["name", "printed_at", "user_name", "product", "client", "template", "copies",
                                  "outcome", "error_code"])
    items = [{"id": r.name, "printed_at": stamp(r.printed_at), "user_name": r.user_name, "product": r.product,
              "client": r.client, "template": r.template, "copies": r.copies, "outcome": r.outcome,
              "error_code": r.error_code} for r in rows]
    return {"items": items, "total": frappe.db.count(HISTORY, filters)}


def minutes_since_printed(branch: str, product: str, client: str, within: int) -> int | None:
    """Minutes since this product last went out (not failed) for this client, within `within`."""
    def key(text) -> str:
        return (text or "").strip(" ").lower()

    rows = frappe.get_all(HISTORY, filters={"branch": branch, "outcome": ["!=", "failed"],
                                            "printed_at": [">=", _ago(within)]},
                          fields=["product", "client", "printed_at"])
    times = [r.printed_at for r in rows if key(r.product) == key(product) and key(r.client) == key(client)]
    if not times:
        return None
    return int((frappe.utils.now_datetime() - max(times)).total_seconds() // 60)


# --- batches ---------------------------------------------------------------------------

def start_batch(branch: str, user: str, rows: list[dict], owner: list[int], queue_ids: list) -> str:
    name = secrets.token_urlsafe(16)
    frappe.get_doc({"doctype": BATCH, "name": name, "branch": branch, "user": user, "rows": json.dumps(rows),
                    "batch_owner": json.dumps(owner), "queue_ids": json.dumps(queue_ids)}).insert(
        ignore_permissions=True)
    return name


def take_batch(name: str, user: str) -> dict | None:
    """The batch (removed), if it exists and belongs to this user."""
    b = frappe.db.get_value(BATCH, {"name": name, "user": user}, ["branch", "rows", "batch_owner", "queue_ids"],
                            as_dict=True)
    if b is None:
        return None
    frappe.db.delete(BATCH, {"name": name})
    return {"branch": b.branch, "rows": json.loads(b.rows), "owner": json.loads(b.batch_owner),
            "queue_ids": json.loads(b.queue_ids)}


def settle_unreported(minutes: int = print_rules.UNREPORTED_AFTER_MINUTES) -> None:
    """Batches nobody reported within the time are recorded as "did not print"."""
    stale = frappe.get_all(BATCH, filters={"creation": ["<", _ago(minutes)]}, fields=["name", "branch", "rows"])
    for b in stale:
        frappe.db.delete(BATCH, {"name": b.name})
        record(b.branch, print_rules.unreported(json.loads(b.rows)))


def daily() -> None:
    """Scheduled (hooks.py): settle forgotten batches and drop history older than 30 days."""
    settle_unreported()
    purge()
    frappe.db.commit()
