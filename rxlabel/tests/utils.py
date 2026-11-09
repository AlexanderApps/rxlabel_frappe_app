"""Test helpers: a company with two branch Warehouses, RxLabel users, and
calling commands as the frontend does."""

from __future__ import annotations

import frappe

COMPANY = "RxLabel Test Pharmacy"
ABBR = "RXT"
PASSWORD = "Test-pass-1234"

SETTINGS = "RxLabel Settings"
SETTINGS_FIELDS = ("company", "license_key", "license_expires_at", "terms_version", "terms_accepted_by",
                   "terms_accepted_at", "shared_json")


class KeepsSettings:
    """Put the site's RxLabel Settings (licence, terms, the company's label
    settings) back as they were after the class's tests: tests change them,
    and they may run on a site in use, with a real licence key."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from frappe.utils.password import get_decrypted_password

        saved = {f: frappe.db.get_single_value(SETTINGS, f) for f in SETTINGS_FIELDS}
        key = get_decrypted_password(SETTINGS, SETTINGS, "license_key", raise_exception=False)
        cls.addClassCleanup(_restore_settings, saved, key)


def _restore_settings(saved: dict, key: str | None) -> None:
    from frappe.utils.password import remove_encrypted_password, set_encrypted_password

    frappe.set_user("Administrator")
    frappe.db.set_single_value(SETTINGS, saved)
    if key:
        set_encrypted_password(SETTINGS, SETTINGS, key, "license_key")
    else:
        remove_encrypted_password(SETTINGS, SETTINGS, "license_key")
    frappe.db.commit()


def call(fn, **kwargs):
    """Run a command as one request would: returns (status, reply); a success
    is committed, an error leaves nothing (the command rolls back)."""
    frappe.local.response = frappe._dict()
    result = fn(**kwargs)
    status = frappe.local.response.get("http_status_code") or 200
    if status != 200:
        return status, {"code": frappe.local.response.get("code"), "message": result}
    frappe.db.commit()
    return 200, result


def ok(fn, **kwargs):
    status, reply = call(fn, **kwargs)
    assert status == 200, reply
    return reply


def default_company() -> str | None:
    """The site's default company (Global Defaults), else its first; None on a site without one."""
    try:
        name = frappe.db.get_single_value("Global Defaults", "default_company")
    except Exception:  # noqa: BLE001 - no Global Defaults (the simulator)
        name = None
    if name and frappe.db.exists("Company", name):
        return name
    first = frappe.get_all("Company", pluck="name", order_by="creation asc", limit=1)
    return first[0] if first else None


def ensure_company() -> str:
    """The site's own company; a test company only on a site without one."""
    existing = default_company()
    if existing:
        return existing
    frappe.get_doc({"doctype": "Company", "company_name": COMPANY, "abbr": ABBR,
                    "default_currency": "GHS", "country": "Ghana"}).insert(ignore_permissions=True)
    return COMPANY


def ensure_branch(name: str, **details) -> str:
    """A non-group Warehouse (a branch) of the site's company."""
    company = ensure_company()
    full = f"{name} - {frappe.db.get_value('Company', company, 'abbr')}"
    if not frappe.db.exists("Warehouse", full):
        frappe.get_doc({"doctype": "Warehouse", "warehouse_name": name, "company": company,
                        **details}).insert(ignore_permissions=True)
    elif details:
        frappe.db.set_value("Warehouse", full, details)
    return full


def ensure_user(email: str, role: str | None, branches: list[str] = (), default: str | None = None) -> str:
    if not frappe.db.exists("User", email):
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                               "send_welcome_email": 0, "new_password": PASSWORD})
        user.insert(ignore_permissions=True)
    user = frappe.get_doc("User", email)
    user.roles = []
    if role:
        user.append("roles", {"role": role})
    user.save(ignore_permissions=True)
    frappe.db.delete("User Permission", {"user": email, "allow": "Warehouse"})
    for b in branches:
        frappe.get_doc({"doctype": "User Permission", "user": email, "allow": "Warehouse", "for_value": b,
                        "is_default": int(b == default)}).insert(ignore_permissions=True)
    frappe.db.delete("RxLabel User Settings", {"user": email})
    frappe.db.delete("RxLabel Branch Settings", {"branch": ["in", branches]}) if branches else None
    return email
