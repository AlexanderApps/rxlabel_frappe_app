"""Demo data: two branches (Warehouses of the site's company; a test
company only on a site without one) and one account of each kind (the
accounts the tests and sim/conformance.py use).

On a bench (after the ERPNext setup wizard):
    bench --site <site> execute rxlabel.tests.demo.seed
In the simulator it is loaded by `run.py reset`.
"""

from __future__ import annotations

import frappe

from .. import install
from .utils import PASSWORD, ensure_branch, ensure_user

OSU = dict(address_line_1="12 Oxford St", city="Accra", phone_no="030 200 0001")
TEMA = dict(address_line_1="Community 1", city="Tema", phone_no="030 300 0002")

# email, RxLabel role, what it shows
ACCOUNTS = [
    ("rx-admin@example.com", "RxLabel Admin", "admin; no branch permissions, so every branch"),
    ("rx-manager@example.com", "RxLabel Manager", "manager at Osu and Tema (Tema by default)"),
    ("rx-user@example.com", "RxLabel User", "user at Osu"),
    ("rx-lost@example.com", "RxLabel User", "user without a branch"),
    ("rx-none@example.com", None, "no RxLabel role: can't sign in"),
]


def seed() -> dict:
    install.ensure_roles()
    osu = ensure_branch("Osu Pharmacy", **OSU)
    tema = ensure_branch("Tema Pharmacy", **TEMA)
    branches = {
        "rx-admin@example.com": ([], None),
        "rx-manager@example.com": ([osu, tema], tema),
        "rx-user@example.com": ([osu], None),
        "rx-lost@example.com": ([], None),
        "rx-none@example.com": ([osu], None),
    }
    for email, role, _ in ACCOUNTS:
        ensure_user(email, role, *branches[email])
    frappe.db.commit()
    return {"password": PASSWORD, "accounts": [a[0] for a in ACCOUNTS], "branches": [osu, tema]}
