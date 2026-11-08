"""The @command decorator: a whitelisted Frappe method with RxLabel's errors."""

from __future__ import annotations

import functools
import re

import frappe
from rxlabel_core.errors import AppError, unique_message


def _plain(message: str) -> str:
    return re.sub(r"<[^>]+>", "", str(message or "")).strip()


def to_app_error(e: Exception) -> AppError | None:
    """Frappe's own errors in RxLabel's terms (None: not an expected error)."""
    if isinstance(e, AppError):
        return e
    if isinstance(e, frappe.PermissionError):
        return AppError("FORBIDDEN", "You don't have permission to do that.")
    if isinstance(e, frappe.DoesNotExistError):
        return AppError("NOT_FOUND", "Not found.")
    if isinstance(e, (frappe.DuplicateEntryError, frappe.UniqueValidationError)):
        return AppError("CONFLICT", _plain(str(e)) or unique_message(""))
    if isinstance(e, frappe.ValidationError):
        return AppError("VALIDATION", _plain(str(e)) or "Invalid data.")
    return None


def reply_error(err: AppError):
    """Make this request answer with `err`, after undoing its changes."""
    frappe.db.rollback()
    frappe.clear_messages()
    frappe.local.response.http_status_code = err.status
    frappe.local.response["exc_type"] = "RxLabelError"
    frappe.local.response["code"] = err.code
    return err.message


def command(fn=None, *, allow_guest: bool = False, methods: tuple[str, ...] = ("POST",)):
    """Register an RxLabel command (POST only unless `methods` says otherwise).

    Frappe lets guests reach every command, so that a signed-out browser gets
    RxLabel's UNAUTHORIZED (and shows the sign-in page) rather than Frappe's
    403; this wrapper turns guests away unless `allow_guest`."""

    def wrap(fn):
        @functools.wraps(fn)
        def run(*args, **kwargs):
            try:
                if not allow_guest and frappe.session.user in (None, "Guest"):
                    raise AppError("UNAUTHORIZED", "Please sign in.")
                return fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001 - expected errors become RxLabel errors
                err = to_app_error(e)
                if err is None:
                    raise
                return reply_error(err)

        run.rxlabel_allow_guest = allow_guest
        return frappe.whitelist(allow_guest=True, methods=list(methods))(run)

    return wrap(fn) if fn is not None else wrap
