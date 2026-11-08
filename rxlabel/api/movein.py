"""Admin > Move data in: a pharmacy's labels and clients from RxLabel desktop
or the standalone app (their export), into a branch. Checking the files
changes nothing; moving them in is all or nothing."""

from __future__ import annotations

import frappe
from rxlabel_core import access, move_in
from rxlabel_core.errors import AppError

from .. import branches, checks, licensing, movein, session
from .base import command


def _uploads() -> list[tuple[str, bytes]]:
    request = frappe.request
    files = request.files.getlist("files") if request is not None and request.files else []
    if not files:
        raise AppError("VALIDATION", "Choose the export's zip, or its files.")
    return [(f.filename or "", f.stream.read()) for f in files]


@command
def move_in_data(branch: str, apply: bool | str = False) -> dict:
    """The export's files come as form data ("files"). Without `apply`: what
    would happen. With it: done, and the same summary."""
    me = session.require(access.ADMINS)
    if branch not in branches.allowed(me["id"]):
        raise AppError("FORBIDDEN", "You don't have access to that branch.")
    data = move_in.read_export(_uploads())
    p = movein.plan(data, branch)
    if checks.flag(apply):
        licensing.require_active()
        movein.apply(p)
    p.pop("_work")
    return {**p, "applied": checks.flag(apply)}
