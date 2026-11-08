"""The company's RxLabel licence (RxLabel Settings) and read-only mode.

One key covers the company and all its branches. With an expired or missing
licence RxLabel still opens (sign in, view, search, history), but printing
and changes are refused with LICENSE_EXPIRED, as on the desktop.
"""

from __future__ import annotations

import time
from typing import Any

import frappe
from rxlabel_core import license
from rxlabel_core.errors import AppError

SETTINGS = "RxLabel Settings"


def public_key() -> bytes:
    """RxLabel's public key (tests replace this function)."""
    return license.PUBLIC_KEY


def verify(key: str) -> dict[str, Any]:
    return license.verify(str(key or ""), now=int(time.time()), public_key=public_key())


def expiry() -> int | None:
    exp = frappe.db.get_single_value(SETTINGS, "license_expires_at")
    return int(exp) if exp else None


def expired() -> bool:
    return license.is_expired(expiry(), time.time())


def require_active() -> None:
    """Refuse printing and changes while the licence is expired."""
    if expired():
        raise AppError("LICENSE_EXPIRED", license.READ_ONLY_MESSAGE)


def save(key: str, payload: dict[str, Any]) -> None:
    settings = frappe.get_single(SETTINGS)
    settings.license_key = key.strip()
    settings.license_expires_at = int(payload["exp"])
    settings.save(ignore_permissions=True)
