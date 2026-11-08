"""Settings: the branch's (facility details, date format, queue size, alert
sound, label and printing settings), and the theme (each user's)."""

from __future__ import annotations

from typing import Any

import frappe
from rxlabel_core import access, date_formats, queue_rules
from rxlabel_core.errors import AppError

from .. import branches, prefs, session
from ..checks import stamp
from .base import command

FACILITY = ("facility_name", "facility_address", "facility_contact")


@command(allow_guest=True)
def get_theme() -> str:
    # Readable before sign-in (the sign-in page uses it): "system" for guests.
    user = frappe.session.user
    if user in (None, "Guest"):
        return "system"
    return prefs.user_pref(user, "theme", "system")


@command(allow_guest=True)
def set_theme(theme: str) -> None:
    if theme not in access.THEMES:
        raise AppError("VALIDATION", "Unknown theme")
    user = frappe.session.user
    if user not in (None, "Guest"):  # before sign-in the browser keeps it
        prefs.set_user_pref(user, "theme", theme)


@command
def get_settings() -> dict | None:
    me = session.require()
    return branch_settings(branches.current(me["id"]))


def branch_settings(branch: str) -> dict:
    """The branch's settings as the standalone app's settings row (labels print its facility details)."""
    facility = branches.facility(branch)
    saved = prefs.branch_fields(branch) or frappe._dict()
    return {"id": 1, "facility_name": facility["facility_name"], "facility_address": facility["facility_address"],
            "facility_contact": facility["facility_contact"],
            "queue_size": saved.queue_size or queue_rules.DEFAULT_QUEUE_SIZE,
            "date_format": date_formats.or_default(saved.date_format),
            "alert_sound": 1 if saved.alert_sound is None else saved.alert_sound,
            "created_at": stamp(saved.creation)}


@command
def save_settings(data: dict) -> None:
    """Fields left out (None) keep their value. Facility details and the queue
    size are an admin's; a facility detail equal to the Warehouse's own is not
    kept as an override, so later changes to the Warehouse show."""
    me = session.require()
    branch = branches.current(me["id"])
    data = dict(data or {}) if isinstance(data, dict) else {}
    values: dict[str, Any] = {}
    if data.get("date_format") is not None:
        values["date_format"] = date_formats.check(data["date_format"])
    if data.get("alert_sound") is not None:
        values["alert_sound"] = 1 if data["alert_sound"] else 0
    if me["role"] == access.ADMIN:
        if data.get("queue_size") is not None:
            try:
                values["queue_size"] = max(1, int(data["queue_size"]))
            except (TypeError, ValueError):
                raise AppError("VALIDATION", "Queue size must be a number.") from None
        own = branches.facility(branch, overrides=False)
        for k in FACILITY:
            v = data.get(k)
            if v is None:
                continue
            if not isinstance(v, str) or len(v) > (140 if k != "facility_address" else 1000):
                raise AppError("VALIDATION", "Facility details are too long.")
            values[k] = None if v.strip() == (own.get(k) or "").strip() else v
    if values:
        prefs.set_branch_fields(branch, values)


@command
def get_aux_setting(key: str) -> Any:
    me = session.require()
    if access.is_internal_aux_key(key) and me["role"] != access.ADMIN:
        raise AppError("FORBIDDEN", f"Setting '{key}' is restricted")
    return prefs.get(key, branches.current(me["id"]))


@command
def set_aux_setting(key: str, value: Any) -> None:
    if key in access.USER_AUX_KEYS:
        me = session.require()
    elif key in access.ADMIN_AUX_KEYS:
        me = session.require(access.ADMINS)
    else:
        raise AppError("FORBIDDEN", f"Setting '{key}' cannot be changed")
    prefs.set_(key, value, branches.current(me["id"]))


@command
def get_all_aux_settings() -> dict:
    me = session.require()
    return prefs.get_all(branches.current(me["id"]))
