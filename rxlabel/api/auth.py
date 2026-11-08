"""Sign-in, sign-out and the current user, on Frappe's own sessions."""

from __future__ import annotations

import frappe
from frappe.auth import LoginManager
from frappe.utils.password import check_password, update_password
from rxlabel_core import access
from rxlabel_core.errors import AppError

from .. import session
from ..branches import branch_info
from .base import command


def _new_csrf_token() -> None:
    # The session (and its CSRF token) changes at sign-in; the page keeps working with the new one.
    frappe.local.response["csrf_token"] = frappe.sessions.get_csrf_token()


@command(allow_guest=True)
def login(username: str, password: str) -> None:
    manager = LoginManager()
    try:
        manager.authenticate(user=username, pwd=password)
    except frappe.SecurityException as e:  # too many attempts
        raise AppError("RATE_LIMITED", str(e) or "Too many failed attempts. Try again later.") from None
    except frappe.AuthenticationError:
        raise AppError("INVALID_CREDENTIALS", "Invalid username or password.") from None
    manager.post_login()
    try:
        session.current_user()  # an account without an RxLabel role can't sign in here
    except AppError:
        manager.logout()
        raise
    _new_csrf_token()


@command(allow_guest=True)
def logout() -> None:
    if frappe.session.user != "Guest":
        LoginManager().logout()
    _new_csrf_token()


@command
def get_me() -> dict:
    me = session.current_user()
    return {**me, "branch": branch_info(me["id"])}


@command
def change_password(current_password: str, new_password: str) -> None:
    """The signed-in user's Frappe password (also their ERPNext password)."""
    me = session.current_user()
    access.validate_new_password(new_password)
    try:
        check_password(me["id"], current_password or "")
    except frappe.AuthenticationError:
        raise AppError("INVALID_CREDENTIALS", "Current password is incorrect") from None
    update_password(me["id"], new_password, logout_all_sessions=False)
