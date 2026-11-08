"""The signed-in user, in the shape the frontend knows (get_me)."""

from __future__ import annotations

import frappe
from rxlabel_core.access import ANY
from rxlabel_core.errors import AppError

from .access import rxlabel_role


def current_user() -> dict:
    """The signed-in RxLabel user; UNAUTHORIZED for guests, FORBIDDEN for
    users without an RxLabel role."""
    user = frappe.session.user
    if not user or user == "Guest":
        raise AppError("UNAUTHORIZED", "Please sign in.")
    role = rxlabel_role(user)
    if role is None:
        raise AppError("FORBIDDEN", "Your account has no RxLabel role. Ask your administrator.")
    full_name, email = frappe.db.get_value("User", user, ["full_name", "email"]) or (user, None)
    return {"id": user, "name": full_name or user, "email": email, "role": role, "position": None}


def require(roles=ANY) -> dict:
    me = current_user()
    if me["role"] not in roles:
        raise AppError("FORBIDDEN", "You don't have permission to do that.")
    return me
