"""Branches. A branch is an ERPNext Warehouse (the pharmacy's stock point at
that branch). Labels print the branch's name, address and phone; clients,
the print queue, print history and label settings belong to a branch.

A user's branches are the Warehouses in their User Permissions; the default
one (or the only one) is used unless they pick another in RxLabel. An RxLabel
admin without Warehouse permissions may use any branch.
"""

from __future__ import annotations

import frappe
from rxlabel_core import access
from rxlabel_core.errors import AppError

from .access import rxlabel_role

SETTINGS = "RxLabel Branch Settings"
USER_SETTINGS = "RxLabel User Settings"


def _all_branches() -> list[str]:
    return frappe.get_all("Warehouse", filters={"is_group": 0, "disabled": 0}, pluck="name", order_by="name")


def allowed(user: str) -> list[str]:
    """The branches `user` may work in, default first."""
    perms = frappe.get_all("User Permission", filters={"user": user, "allow": "Warehouse"},
                           fields=["for_value", "is_default"], order_by="is_default desc, creation asc")
    names = [p.for_value for p in perms if frappe.db.exists("Warehouse", {"name": p.for_value, "is_group": 0})]
    if not names and rxlabel_role(user) == access.ADMIN:
        return _all_branches()
    return list(dict.fromkeys(names))


def current(user: str | None = None) -> str:
    """The branch `user` is working in now; FORBIDDEN when they have none."""
    user = user or frappe.session.user
    choices = allowed(user)
    if not choices:
        raise AppError("FORBIDDEN", "You don't have a branch yet. Ask your administrator to give you "
                                    "access to your branch's Warehouse (User Permission).")
    chosen = frappe.db.get_value(USER_SETTINGS, user, "branch")
    return chosen if chosen in choices else choices[0]


def choose(user: str, branch: str) -> None:
    if branch not in allowed(user):
        raise AppError("FORBIDDEN", "You don't have access to that branch.")
    if frappe.db.exists(USER_SETTINGS, user):
        frappe.db.set_value(USER_SETTINGS, user, "branch", branch)
    else:
        frappe.get_doc({"doctype": USER_SETTINGS, "user": user, "branch": branch}).insert(ignore_permissions=True)


def facility(branch: str, overrides: bool = True) -> dict:
    """What labels say about the branch: its name, address and phone. The
    branch's RxLabel settings may override the Warehouse's details
    (`overrides=False`: the Warehouse's own)."""
    wh = frappe.db.get_value("Warehouse", branch, ["warehouse_name", "address_line_1", "address_line_2",
                                                   "city", "state", "phone_no", "mobile_no", "company"],
                             as_dict=True) or {}
    over = (frappe.db.get_value(SETTINGS, branch, ["facility_name", "facility_address", "facility_contact"],
                                as_dict=True) or {}) if overrides else {}
    address = ", ".join(p for p in (wh.get("address_line_1"), wh.get("address_line_2"), wh.get("city"),
                                    wh.get("state")) if p)
    return {
        "facility_name": over.get("facility_name") or wh.get("warehouse_name") or branch,
        "facility_address": over.get("facility_address") or address,
        "facility_contact": over.get("facility_contact") or wh.get("phone_no") or wh.get("mobile_no") or "",
        "company": wh.get("company"),
    }


def branch_info(user: str) -> dict | None:
    """The current branch and the choices, for the app header; None without a branch."""
    try:
        branch = current(user)
    except AppError:
        return None
    return {"name": branch, **facility(branch), "choices": allowed(user)}
