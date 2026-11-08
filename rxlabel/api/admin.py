"""The admin console under ERPNext: who uses RxLabel, an overview, and the
support file. Accounts, backups and the database are ERPNext's (Desk and the
bench), so RxLabel only shows them here."""

from __future__ import annotations

import json
import platform
from datetime import datetime

import frappe
from rxlabel_core import access, diagnostics

from .. import __version__, branches, licensing, prefs, printqueue, session
from ..access import ROLES, rxlabel_role
from ..checks import stamp
from .base import command

MAX_REPORT_CHARS = 20_000


def _versions() -> dict:
    try:
        import erpnext
        erpnext_version = erpnext.__version__
    except ImportError:
        erpnext_version = None
    return {"app_version": __version__, "frappe_version": frappe.__version__, "erpnext_version": erpnext_version}


def _rxlabel_users() -> list[str]:
    """Everyone with an RxLabel role (System Managers count as RxLabel admins)."""
    names = set(frappe.get_all("Has Role", filters={"parenttype": "User",
                                                    "role": ["in", [*ROLES, "System Manager"]]}, pluck="parent"))
    return sorted(names - {"Administrator", "Guest"})


@command
def get_users() -> list[dict]:
    """Read-only: accounts are managed in ERPNext (User, its roles, and a User
    Permission on each branch's Warehouse). Only an admin sees admins."""
    me = session.require(access.STAFF)
    names = _rxlabel_users()
    if not names:
        return []
    rows = frappe.get_all("User", filters={"name": ["in", names]}, order_by="creation desc, name desc",
                          fields=["name", "full_name", "email", "enabled", "creation"])
    out = []
    for r in rows:
        role = rxlabel_role(r.name)
        if role is None or (role == access.ADMIN and me["role"] != access.ADMIN):
            continue
        explicit = frappe.db.count("User Permission", {"user": r.name, "allow": "Warehouse"}) > 0
        out.append({"id": r.name, "name": r.full_name or r.name, "email": r.email, "secret": None, "role": role,
                    "position": None, "created_at": stamp(r.creation), "enabled": bool(r.enabled),
                    "branches": branches.allowed(r.name) if explicit else [],
                    "all_branches": not explicit and role == access.ADMIN})
    return out


def _counts(branch: str) -> dict:
    return {"num_labels": frappe.db.count("RxLabel Label"),
            "num_clients": frappe.db.count("RxLabel Client", {"branch": branch}),
            "num_users": len(_rxlabel_users())}


@command
def get_general_stats() -> dict:
    """The overview: counts (clients and queue: this branch), versions, where."""
    me = session.require(access.STAFF)
    branch = branches.current(me["id"])
    return {**_counts(branch), **_versions(), "host": "frappe", "site": frappe.local.site if hasattr(
        frappe.local, "site") else None, "branch": branch, "company": branches.facility(branch)["company"],
        "license_expires_at": licensing.expiry()}


@command
def export_diagnostics(printer_status: dict | None = None, printer_report: str | None = None) -> None:
    """A zip for support: versions, licence, counts and settings (no labels,
    client details or passwords) and the browser's printing check. The
    server's logs are the bench's (bench/logs)."""
    me = session.require(access.ADMINS)
    branch = branches.current(me["id"])
    saved = prefs.branch_fields(branch) or frappe._dict()
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "app": "RxLabel for ERPNext",
        **_versions(),
        "os": platform.system().lower(),
        "python": platform.python_version(),
        "license": {"company": branches.facility(branch)["company"], "expires_at": licensing.expiry(),
                    "expired": licensing.expired()},
        "printer": {"status": printer_status} if isinstance(printer_status, dict)
        else {"status": "not reported by the browser"},
        "branch": branch,
        "counts": {**_counts(branch), "queue": printqueue.count(branch),
                   "print_history": frappe.db.count("RxLabel Print History", {"branch": branch})},
        "settings": {"queue_size": saved.queue_size, "date_format": saved.date_format,
                     "alert_sound": saved.alert_sound},
        "app_settings": diagnostics.safe_settings(prefs.get_all(branch)),
    }
    report = printer_report[:MAX_REPORT_CHARS] if isinstance(printer_report, str) else None
    data = diagnostics.build_zip(json.loads(json.dumps(summary, default=str)), [], report)
    frappe.local.response.update({"type": "download", "filename":
                                  f"RxLabel-diagnostics-{datetime.now().strftime('%Y%m%d-%H%M')}.zip",
                                  "filecontent": data, "content_type": "application/zip"})
