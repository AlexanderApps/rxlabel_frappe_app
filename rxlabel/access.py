"""Who may use RxLabel, and as which RxLabel role.

Frappe roles map onto RxLabel's three (rxlabel_core.access):
  RxLabel Admin (or System Manager) -> admin
  RxLabel Manager                   -> manager
  RxLabel User                      -> user
A user with none of these can't use RxLabel.
"""

from __future__ import annotations

import frappe
from rxlabel_core import access

ADMIN_ROLE, MANAGER_ROLE, USER_ROLE = "RxLabel Admin", "RxLabel Manager", "RxLabel User"
ROLES = (ADMIN_ROLE, MANAGER_ROLE, USER_ROLE)


def rxlabel_role(user: str | None = None) -> str | None:
    """admin / manager / user, or None."""
    user = user or frappe.session.user
    if not user or user == "Guest":
        return None
    roles = set(frappe.get_roles(user))
    if user == "Administrator" or ADMIN_ROLE in roles or "System Manager" in roles:
        return access.ADMIN
    if MANAGER_ROLE in roles:
        return access.MANAGER
    if USER_ROLE in roles:
        return access.USER
    return None


def can_use(user: str | None = None) -> bool:
    """For the apps screen (hooks.add_to_apps_screen)."""
    return rxlabel_role(user) is not None
