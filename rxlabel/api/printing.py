"""Printing. The browser prints (frontend/src/printing): printer status, the
printer list, printing and the preview itself. The server builds the jobs
from the branch's label settings and details, records the outcomes in the
branch's history, and gives the warnings."""

from __future__ import annotations

import frappe
from rxlabel_core import access, label_checks, label_image, label_jobs, label_settings, print_rules
from rxlabel_core.errors import AppError
from rxlabel_core.print_rules import KEEP_DAYS, MAX_HISTORY_ROWS

from .. import branches, checks, history, licensing, prefs, printqueue, session
from .base import command
from .settings import branch_settings

CLIENT = "RxLabel Client"
CLIENT_LABEL = "RxLabel Client Label"


def _label_settings(branch: str) -> dict:
    return label_settings.label_settings_from_saved(prefs.get("label_settings", branch))


def _calibration(branch: str) -> dict:
    return label_settings.calibration_from_saved(prefs.get("print_calibration", branch))


def _dpi(dpi: object) -> int:
    """The printer's resolution as the browser reports it; 203 when unknown."""
    return dpi if isinstance(dpi, int) and not isinstance(dpi, bool) and 100 <= dpi <= 1200 \
        else label_image.DEFAULT_DPI


def _globals(branch: str, user: dict) -> dict:
    return {**print_rules.as_vars(branch_settings(branch)), "user_name": user["name"]}


def _client_labels(branch: str, client_id) -> list[dict]:
    """A client's labels as print values (product, instructions, warning, client name); none if not this branch's."""
    cid = checks.ident(client_id)
    name = frappe.db.get_value(CLIENT, {"name": cid, "branch": branch}, "client_name")
    if name is None:
        return []
    rows = frappe.get_all(CLIENT_LABEL, filters={"client": cid}, fields=["product", "instructions", "warning"],
                          order_by="name asc")
    return [{"product": r.product, "instructions": r.instructions, "warning": r.warning, "client": name}
            for r in rows]


def _build(branch: str, user: dict, vars_list, template, print_type, queue_ids, dpi=None) -> dict:
    if not isinstance(vars_list, list) or not vars_list:
        raise AppError("VALIDATION", "No labels to print.")
    if queue_ids is not None and (not isinstance(queue_ids, list) or len(queue_ids) != len(vars_list)):
        raise AppError("VALIDATION", "queue_ids must match the labels")
    labels = print_rules.merge_globals(vars_list, _globals(branch, user))
    try:
        if print_type == "image":
            jobs = label_image.build_image_jobs(template, labels, _label_settings(branch), _calibration(branch),
                                                _dpi(dpi))
        else:
            jobs = label_jobs.build_jobs(template, labels, _label_settings(branch), _calibration(branch))
    except label_jobs.TemplateError as e:
        raise AppError("VALIDATION", str(e)) from None
    rows = print_rules.history_rows(user, template, labels, [label_jobs.copies_of(v) for v in labels])
    history.settle_unreported()
    batch = history.start_batch(branch, user["id"], rows, [j["label"] for j in jobs],
                                list(queue_ids) if queue_ids else [None] * len(labels))
    return {"batch": batch, "labels": len(labels), "jobs": jobs}


@command
def list_templates() -> list[str]:
    me = session.require()
    return label_settings.templates_for(_label_settings(branches.current(me["id"])))


@command
def list_label_sizes() -> list[dict]:
    session.require(access.ADMINS)
    return label_settings.label_sizes()


@command
def build_print_jobs(vars_list: list[dict], template: str = "base", print_type: str = "json",
                     queue_ids: list[int] | None = None, dpi: int | None = None) -> dict:
    """The print jobs for these labels, one per printed copy:
    {"batch": id, "labels": n, "jobs": [{"label": i, "job": {...}}]}. The
    browser prints them, then reports with record_print."""
    me = session.require()
    licensing.require_active()
    return _build(branches.current(me["id"]), me, vars_list, template, print_type, queue_ids, dpi)


@command
def build_client_print_jobs(client_id: int, timestamp: str = "", template: str = "base", print_type: str = "json",
                            printer_model: str = "", dpi: int | None = None) -> dict:
    """build_print_jobs for all of a client's saved labels."""
    me = session.require()
    licensing.require_active()
    branch = branches.current(me["id"])
    saved = _client_labels(branch, client_id)
    if not saved:
        raise AppError("VALIDATION", "This client has no saved labels to print.")
    vars_list = [{**print_rules.as_vars(label), "timestamp": timestamp, "printer_model": printer_model}
                 for label in saved]
    return _build(branch, me, vars_list, template, print_type, None, dpi)


@command
def record_print(batch: str, results: list[dict]) -> dict:
    """The browser's report on a batch ({index, success, held, code} per job):
    recorded in the history of the branch it was printed for; with "remove
    from the queue after printing" on, the queue items that went out go."""
    me = session.require()
    taken = history.take_batch(str(batch), me["id"])
    if taken is None:
        raise AppError("NOT_FOUND", "That print was already recorded.")
    branch = taken["branch"]
    rows = print_rules.with_outcomes(taken["rows"], taken["owner"], results if isinstance(results, list) else [])
    history.record(branch, rows)
    history.purge(KEEP_DAYS)
    if prefs.get("queue_remove_after_print", branch, False) is True:
        printqueue.remove(branch, [qid for row, qid in zip(rows, taken["queue_ids"])
                                   if row["outcome"] != "failed" and qid is not None])
    return {"recorded": len(rows)}


@command
def get_print_history(days: int = 30) -> dict:
    me = session.require(access.STAFF)
    history.settle_unreported()
    history.purge(KEEP_DAYS)
    try:
        days = max(1, min(KEEP_DAYS, int(days)))
    except (TypeError, ValueError):
        raise AppError("VALIDATION", "days must be a number") from None
    return {**history.recent(branches.current(me["id"]), days, MAX_HISTORY_ROWS), "keep_days": KEEP_DAYS}


def _checks(branch: str, template, labels: list) -> list[dict]:
    settings_ = _label_settings(branch)
    window = int(settings_["double_print_minutes"])

    def recent(product: str, client: str) -> int | None:
        return history.minutes_since_printed(branch, product, client, window) if window else None

    def too_long(values: dict) -> list[str]:
        return label_checks.too_long(str(template), values, settings_)

    return print_rules.check_labels(labels, recent, too_long)


@command
def check_print(template: str, vars_list: list[dict]) -> list[dict]:
    me = session.require()
    return _checks(branches.current(me["id"]), template, vars_list)


@command
def check_client_print(client_id: int, template: str = "base") -> list[dict]:
    me = session.require()
    branch = branches.current(me["id"])
    return _checks(branch, template, [print_rules.as_vars(v) for v in _client_labels(branch, client_id)])


@command
def build_preview_job(vars: dict, template: str = "base", print_type: str = "json", dpi: int | None = None) -> dict:
    """One label for the preview; nothing printed or recorded (allowed when
    read-only). Text printing: {"job", "notes"}; image printing: {"preview"}."""
    me = session.require()
    if not isinstance(vars, dict):
        raise AppError("VALIDATION", "No label to preview.")
    branch = branches.current(me["id"])
    values = {**print_rules.merge_globals([vars], _globals(branch, me))[0], "copies": "1"}
    label_jobs.fill_optional(values)
    settings_ = _label_settings(branch)
    try:
        if print_type == "image":
            threshold = int(_calibration(branch)["threshold"])
            return {"preview": label_image.preview(str(template), values, settings_, _dpi(dpi), threshold)}
        built = label_jobs.build_jobs(str(template), [values], settings_, _calibration(branch))
    except label_jobs.TemplateError as e:
        raise AppError("VALIDATION", str(e)) from None
    return {"job": built[0]["job"], "notes": label_checks.fit_report(str(template), print_rules.as_vars(values),
                                                                     settings_)}


@command
def build_test_label(print_type: str = "json", printer: str = "automatic", dpi: int | None = None) -> dict:
    """Admin > Settings > Printing > "Print test label", with this branch's calibration. Not recorded."""
    me = session.require(access.ADMINS)
    licensing.require_active()
    calibration = _calibration(branches.current(me["id"]))
    kind = "image" if print_type == "image" else "json"
    lines = label_image.test_label_lines(kind, calibration, _dpi(dpi), str(printer)[:80] or "automatic")
    return {"job": label_image.test_label_job(kind, lines, calibration, _dpi(dpi))}
