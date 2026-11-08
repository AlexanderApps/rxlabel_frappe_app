"""Admin > Data > Export: the branch's data as CSV or JSON, in the standalone
app's export format (see ..export). Admins and managers, as in the
standalone app; it works while the licence is expired (read-only still lets
a pharmacy take its data)."""

from __future__ import annotations

import io
import zipfile

import frappe
from rxlabel_core import access
from rxlabel_core import data_transfer as rules
from rxlabel_core.errors import validation

from .. import branches, export, session
from .base import command

MIMETYPES = {"csv": "text/csv; charset=utf-8", "json": "application/json"}


def _branch() -> str:
    me = session.require(access.STAFF)
    return branches.current(me["id"])


def _options(options: object) -> dict:
    if isinstance(options, str):
        options = frappe.parse_json(options)
    if not isinstance(options, dict):
        raise validation("Export options are missing.")
    return options


@command
def get_export_counts(date_from: str | None = None, date_to: str | None = None) -> dict:
    branch = _branch()
    date_range = rules.date_range(date_from, date_to)
    return {t: export.count(t, branch, date_range) for t in sorted(rules.EXPORT_TABLES)}


@command
def get_export_preview(options: dict) -> dict:
    branch = _branch()
    options = _options(options)
    date_range = rules.date_range(options.get("date_from"), options.get("date_to"))
    limit = options.get("limit")
    limit = rules.PREVIEW_ROWS if limit is None else limit
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise validation("The preview size must be a number.")
    columns, rows = export.rows(str(options.get("table")), branch, bool(options.get("include_timestamps")),
                                date_range, limit)
    return {"data": rows, "columns": columns}


@command
def export_data(options: dict) -> None:
    branch = _branch()
    options = _options(options)
    fmt = str(options.get("format"))
    rules.check_format(fmt)
    tables = rules.export_tables(options.get("tables") or [])
    date_range = rules.date_range(options.get("date_from"), options.get("date_to")) \
        if options.get("use_date_filter") else None
    include_timestamps = bool(options.get("include_timestamps"))
    include_headers = bool(options.get("include_headers"))

    files = {}
    for table in tables:
        columns, rows = export.rows(table, branch, include_timestamps, date_range)
        files[table] = rules.export_file(columns, rows, fmt, include_headers)

    separate, name = rules.export_names(tables, fmt, bool(options.get("separate_files")),
                                        frappe.utils.now_datetime())
    if separate:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            for table, data in files.items():
                z.writestr(f"{name}/{table}.{fmt}", data)
        name, data, mimetype = f"{name}.zip", buffer.getvalue(), "application/zip"
    else:
        data, mimetype = files[tables[0]], MIMETYPES[fmt]
    frappe.local.response.update({"type": "download", "filename": name, "filecontent": data,
                                  "content_type": mimetype})
