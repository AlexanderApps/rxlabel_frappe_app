"""A branch's data in the standalone app's export format, so it can go back
into RxLabel desktop or the standalone app (their CSV import) or into
another branch (Move data in).

- labels: the company's library; clients, client labels and the queue: the
  branch's.
- Ids are numbered 1, 2, 3... per table, oldest first, as in a new RxLabel
  database, and client_id points at those numbers. ERPNext's ids are
  site-wide and mean nothing outside it; numbered like this, clients
  imported into an RxLabel with no clients get the same ids, so client
  labels imported next find their client.
- created_at is UTC, YYYY-MM-DD HH:MM:SS, as the standalone app writes it.
"""

from __future__ import annotations

import frappe
from rxlabel_core.data_transfer import EXPORT_COLUMNS, check_export_table

from .checks import number, stamp

LABEL, CLIENT, CLIENT_LABEL, QUEUE = "RxLabel Label", "RxLabel Client", "RxLabel Client Label", "RxLabel Queue Item"


def _numbered(rows: list) -> dict:
    """{ERPNext id: 1, 2, 3...} in id order (ids grow with each record)."""
    return {r.name: i for i, r in enumerate(rows, 1)}


def _all_rows(table: str, branch: str) -> list[dict]:
    """Every row of `table` for `branch`, oldest first, in export columns."""
    if table == "labels":
        rows = frappe.get_all(LABEL, fields=["name", "product", "instructions", "warning", "is_custom", "seed_key",
                                             "creation"], order_by="name asc")
        return [{"id": i, "product": r.product, "instructions": r.instructions, "warning": r.warning,
                 "is_custom": int(r.is_custom or 0), "created_at": stamp(r.creation), "seed_key": r.seed_key}
                for i, r in enumerate(rows, 1)]

    clients = frappe.get_all(CLIENT, filters={"branch": branch},
                             fields=["name", "client_name", "contact", "email", "home_address", "creation"],
                             order_by="name asc")
    client_ids = {number(k): v for k, v in _numbered(clients).items()}
    if table == "clients":
        return [{"id": client_ids[r.name], "name": r.client_name, "contact": r.contact, "email": r.email,
                 "home_address": r.home_address, "created_at": stamp(r.creation)} for r in clients]

    if table == "client_labels":
        rows = frappe.get_all(CLIENT_LABEL, filters={"client": ["in", [str(k) for k in client_ids]]},
                              fields=["client", "product", "instructions", "warning", "creation"],
                              order_by="name asc") if client_ids else []
        return [{"id": i, "client_id": client_ids[number(r.client)], "product": r.product,
                 "instructions": r.instructions, "warning": r.warning, "created_at": stamp(r.creation)}
                for i, r in enumerate(rows, 1)]

    rows = frappe.get_all(QUEUE, filters={"branch": branch},
                          fields=["product", "instructions", "warning", "client", "client_id", "creation"],
                          order_by="name asc")
    return [{"id": i, "product": r.product, "instructions": r.instructions, "warning": r.warning,
             "client": r.client, "created_at": stamp(r.creation),
             "client_id": client_ids.get(number(r.client_id))}
            for i, r in enumerate(rows, 1)]


def _in_range(row: dict, date_range: tuple[str, str] | None) -> bool:
    if date_range is None:
        return True
    start, end = date_range
    return row["created_at"] is not None and start <= row["created_at"] <= f"{end} 23:59:59"


def rows(table: str, branch: str, include_timestamps: bool, date_range: tuple[str, str] | None,
         limit: int | None = None) -> tuple[list[str], list[dict]]:
    """(columns, rows) as the standalone app's export_rows."""
    check_export_table(table)
    columns = [c for c in EXPORT_COLUMNS[table] if include_timestamps or c != "created_at"]
    picked = [r for r in _all_rows(table, branch) if _in_range(r, date_range)]
    if limit is not None:
        picked = picked[:max(0, int(limit))]
    return columns, [{c: r[c] for c in columns} for r in picked]


def count(table: str, branch: str, date_range: tuple[str, str] | None) -> int:
    check_export_table(table)
    if date_range is None:
        if table == "labels":
            return frappe.db.count(LABEL)
        if table == "clients":
            return frappe.db.count(CLIENT, {"branch": branch})
        if table == "queue":
            return frappe.db.count(QUEUE, {"branch": branch})
    return sum(1 for r in _all_rows(table, branch) if _in_range(r, date_range))
