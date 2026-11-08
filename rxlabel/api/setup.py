"""Licence status and renewal. There is no setup wizard in Frappe: the
company, branches (Warehouses) and users are set up in ERPNext."""

from __future__ import annotations

from rxlabel_core import access, license
from rxlabel_core.errors import AppError
from rxlabel_core.terms import TERMS_VERSION

from .. import licensing, session
from .base import command


@command(allow_guest=True)
def check_setup_status() -> dict:
    return {"is_setup_complete": True, "is_license_expired": licensing.expired(),
            "license_expires_at": licensing.expiry()}


@command
def verify_license_key(license_key: str) -> dict:
    session.require(access.ADMINS)
    return license.summary(licensing.verify(license_key))


@command
def update_app_license(data: dict) -> None:
    """Enter or renew the company's licence key (RxLabel admins)."""
    session.require(access.ADMINS)
    key = (data or {}).get("license") if isinstance(data, dict) else None
    if not isinstance(key, str) or not key.strip():
        raise AppError("VALIDATION", "Missing value: license.")
    licensing.save(key, licensing.verify(key))


@command
def get_terms_status() -> dict:
    # Accepted with the licence by the company's administrator.
    session.require()
    return {"version": TERMS_VERSION, "accepted": True}


@command
def accept_terms(version: str) -> None:
    session.require()
