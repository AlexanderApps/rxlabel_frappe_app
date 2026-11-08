"""RxLabel's settings store ("aux settings"), by who a setting belongs to:

- the branch: label and printing settings, the queue's limits, search options
  (RxLabel Branch Settings: its fields, and settings_json for the rest);
- the company: instruction phrases and options, the idle sign-out time
  (RxLabel Settings.shared_json);
- the user: the theme (RxLabel User Settings.preferences).

Same keys and values as the standalone app, so the frontend doesn't change.
Backup keys (backup_*) don't exist here: backups are the bench's.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from rxlabel_core import access, phrases

BRANCH_SETTINGS = "RxLabel Branch Settings"
COMPANY_SETTINGS = "RxLabel Settings"
USER_SETTINGS = "RxLabel User Settings"

COMPANY_KEYS = frozenset({phrases.PHRASES_KEY, phrases.OPTIONS_KEY, access.IDLE_TIMEOUT_KEY, "last_optimization"})


def _loads(raw) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _dumps(values: dict) -> str:
    return json.dumps(values, separators=(",", ":"), sort_keys=True)


# --- company -------------------------------------------------------------------------

def _company() -> dict:
    return _loads(frappe.db.get_single_value(COMPANY_SETTINGS, "shared_json"))


def _save_company(values: dict) -> None:
    frappe.db.set_single_value(COMPANY_SETTINGS, "shared_json", _dumps(values))


# --- branch --------------------------------------------------------------------------

def _branch(branch: str, for_update: bool = False) -> dict:
    return _loads(frappe.db.get_value(BRANCH_SETTINGS, branch, "settings_json", for_update=for_update))


def ensure_branch_settings(branch: str) -> None:
    if not frappe.db.exists(BRANCH_SETTINGS, branch):
        frappe.get_doc({"doctype": BRANCH_SETTINGS, "branch": branch}).insert(ignore_permissions=True)


def set_branch_fields(branch: str, values: dict) -> None:
    """Branch Settings' own fields (queue_size, date_format, alert_sound, facility overrides)."""
    ensure_branch_settings(branch)
    doc = frappe.get_doc(BRANCH_SETTINGS, branch)
    doc.update(values)
    doc.save(ignore_permissions=True)


def branch_fields(branch: str) -> dict | None:
    return frappe.db.get_value(BRANCH_SETTINGS, branch, ["facility_name", "facility_address", "facility_contact",
                                                         "queue_size", "date_format", "alert_sound", "creation"],
                               as_dict=True)


# --- aux settings ----------------------------------------------------------------------

def get(key: str, branch: str, default: Any = None) -> Any:
    if access.is_internal_aux_key(key):
        return default
    values = _company() if key in COMPANY_KEYS else _branch(branch)
    return values.get(key, default)


def set_(key: str, value: Any, branch: str) -> None:
    """None removes the setting (as in the standalone app)."""
    if key in COMPANY_KEYS:
        values = _company()
        values.pop(key, None) if value is None else values.__setitem__(key, value)
        _save_company(values)
        return
    ensure_branch_settings(branch)
    values = _branch(branch, for_update=True)
    values.pop(key, None) if value is None else values.__setitem__(key, value)
    frappe.db.set_value(BRANCH_SETTINGS, branch, "settings_json", _dumps(values))


def get_all(branch: str) -> dict:
    return {**_company(), **_branch(branch)}


# --- the user's own ---------------------------------------------------------------------

def user_pref(user: str, key: str, default: Any = None) -> Any:
    return _loads(frappe.db.get_value(USER_SETTINGS, user, "preferences")).get(key, default)


def set_user_pref(user: str, key: str, value: Any) -> None:
    if not frappe.db.exists(USER_SETTINGS, user):
        frappe.get_doc({"doctype": USER_SETTINGS, "user": user}).insert(ignore_permissions=True)
    values = _loads(frappe.db.get_value(USER_SETTINGS, user, "preferences", for_update=True))
    values[key] = value
    frappe.db.set_value(USER_SETTINGS, user, "preferences", _dumps(values))
