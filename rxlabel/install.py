"""Install and migrate: the RxLabel roles, the preloaded label library and
the company-wide settings."""

from __future__ import annotations

import sqlite3
from importlib import resources

import frappe

from .access import ROLES

LABEL = "RxLabel Label"


def after_install() -> None:
    ensure_roles()
    load_preloaded_labels()


def after_migrate() -> None:
    ensure_roles()


def ensure_roles() -> None:
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def preloaded_labels() -> list[tuple[str, str | None, str | None, str]]:
    """The preloaded labels (the desktop's labels.sql) with their seed keys:
    the normalised product name, plus #n for the 2nd, 3rd... with the same name."""
    sql = resources.files("rxlabel_core.data").joinpath("labels.sql").read_text(encoding="utf-8")
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE labels (id INTEGER PRIMARY KEY, product TEXT, instructions TEXT, warning TEXT)")
    db.executescript(sql)
    rows = db.execute(
        """SELECT product, instructions, warning,
                  lower(trim(product)) || CASE WHEN rn > 1 THEN '#' || rn ELSE '' END
             FROM (SELECT id, product, instructions, warning,
                          ROW_NUMBER() OVER (PARTITION BY lower(trim(product)) ORDER BY id) AS rn
                     FROM labels)
            ORDER BY id"""
    ).fetchall()
    db.close()
    return rows


def load_preloaded_labels() -> int:
    """Fill an empty label library. Returns how many labels were added."""
    if frappe.db.count(LABEL):
        return 0
    now = frappe.utils.now()
    user = frappe.session.user or "Administrator"
    # Autoincrement names come from the DocType's sequence.
    values = [(frappe.db.get_next_sequence_val(LABEL), product, instructions, warning, 0, seed_key,
               now, now, user, user)
              for product, instructions, warning, seed_key in preloaded_labels()]
    frappe.db.bulk_insert(LABEL, ["name", "product", "instructions", "warning", "is_custom", "seed_key",
                                  "creation", "modified", "owner", "modified_by"], values)
    return len(values)
