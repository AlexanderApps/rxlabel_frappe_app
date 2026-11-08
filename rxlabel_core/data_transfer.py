"""CSV import and data export rules (the desktop's commands/data_transfer.rs
and db.rs import_csv_data / export_rows). No database or files here.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from .errors import validation

# Tables the export screen may read, and their columns in the desktop's
# order (a desktop database: the baseline, then later columns at the end).
EXPORT_COLUMNS: dict[str, tuple[str, ...]] = {
    "labels": ("id", "product", "instructions", "warning", "is_custom", "created_at", "seed_key"),
    "clients": ("id", "name", "contact", "email", "home_address", "created_at"),
    "client_labels": ("id", "client_id", "product", "instructions", "warning", "created_at"),
    "queue": ("id", "product", "instructions", "warning", "client", "created_at", "client_id"),
}
EXPORT_TABLES = tuple(EXPORT_COLUMNS)
EXPORT_FORMATS = ("csv", "json")
PREVIEW_ROWS = 5

# Columns a CSV import may set, per table (ImportDataView.vue tableSchemas).
# id, created_at and is_custom are never imported.
IMPORT_COLUMNS: dict[str, tuple[str, ...]] = {
    "labels": ("product", "instructions", "warning"),
    "clients": ("name", "contact", "email", "home_address"),
    "client_labels": ("client_id", "product", "instructions", "warning"),
    "queue": ("product", "instructions", "warning", "client"),
}


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return len(value) == 10


def date_range(date_from: str | None, date_to: str | None) -> tuple[str, str] | None:
    """An inclusive created_at range: both ends as YYYY-MM-DD, or none at all."""
    if not date_from or not date_to:
        return None
    if not _is_date(date_from) or not _is_date(date_to):
        raise validation("Dates must be in YYYY-MM-DD format")
    if date_from > date_to:
        raise validation("The start date is after the end date")
    return date_from, date_to


def check_export_table(table: str) -> None:
    if table not in EXPORT_COLUMNS:
        raise validation(f"Unknown table '{table}'")


def export_tables(requested: list) -> list[str]:
    """The requested tables that may be exported, in the order asked."""
    tables = [t for t in requested if isinstance(t, str) and t in EXPORT_COLUMNS]
    if not tables:
        raise validation("No valid tables selected")
    return list(dict.fromkeys(tables))


def check_format(fmt: str) -> None:
    if fmt not in EXPORT_FORMATS:
        raise validation(f"Unsupported export format '{fmt}'")


def csv_field(value) -> str:
    """RFC 4180 quoting; null is empty (data_transfer.rs csv_field)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        s = "true" if value else "false"
    elif isinstance(value, str):
        s = value
    else:
        s = json.dumps(value)
    if any(c in s for c in ',"\n\r'):
        return '"' + s.replace('"', '""') + '"'
    return s


def to_csv(columns: list[str], rows: list[dict], include_headers: bool) -> str:
    lines = []
    if include_headers:
        lines.append(",".join(csv_field(c) for c in columns))
    for row in rows:
        lines.append(",".join(csv_field(row.get(c)) for c in columns))
    return "".join(f"{line}\r\n" for line in lines)


def to_json(rows: list[dict]) -> str:
    # As serde_json::to_writer_pretty with the desktop's default (sorted) maps.
    return json.dumps(rows, indent=2, ensure_ascii=False, sort_keys=True)


def export_file(columns: list[str], rows: list[dict], fmt: str, include_headers: bool) -> bytes:
    text = to_json(rows) if fmt == "json" else to_csv(columns, rows, include_headers)
    return text.encode("utf-8")


def export_names(tables: list[str], fmt: str, separate_files: bool, now: datetime) -> tuple[bool, str]:
    """(one file per table?, download name). Several files come as a zip of a
    folder named like the desktop's export folder."""
    stamp = now.strftime("%Y%m%d_%H%M%S")
    if separate_files or len(tables) > 1:
        return True, f"rxlabel_export_{stamp}"
    return False, f"{tables[0]}_{stamp}.{fmt}"


def import_rows(table: str, data: object) -> list[dict]:
    """The rows to insert: checked columns, and in each row only the values
    given (null and empty text are left to the column default). Rows with
    nothing in them are skipped. Column names come from CSV headers, so any
    unknown one rejects the whole import."""
    allowed = IMPORT_COLUMNS.get(table)
    if allowed is None:
        raise validation(f"cannot import into '{table}'")
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise validation("The rows to import must be a list of objects.")
    unknown = sorted({k for row in data for k in row if k not in allowed})
    if unknown:
        raise validation(f"cannot import into '{table}': unknown column(s) {', '.join(unknown)}; "
                         f"allowed: {', '.join(allowed)}")
    rows = []
    for row in data:
        values = {k: sql_value(v) for k, v in row.items() if v is not None and v != ""}
        if values:
            rows.append(values)
    return rows


def sql_value(value):
    """A JSON value as stored (db.rs json_to_sql_value)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return value
    return json.dumps(value)
