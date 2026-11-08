"""Reading a pharmacy's export from RxLabel desktop or the standalone app
(Admin > Database > Export), to move their labels and clients somewhere
else, e.g. into ERPNext. No database here: this turns the files into rows.

Accepted: the standalone app's zip, or the files themselves (the desktop
saves a folder of them), named as the export names them: labels.csv,
clients.csv, client_labels.csv, or .json, with or without the export's
date stamp (labels_20261107_093000.csv). CSV needs its column headers
(the export's "Include headers"): without them the columns can't be told
apart across RxLabel versions. Queue files are ignored.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import PurePosixPath

from .data_transfer import EXPORT_COLUMNS
from .errors import validation

TABLES = ("labels", "clients", "client_labels")
MAX_BYTES = 50 * 1024 * 1024        # all files together, unpacked
MAX_ROWS = 100_000                  # per table

_NAME = re.compile(r"^(client_labels|clients|labels|queue)(?:_\d{8}_\d{6})?\.(csv|json)$")
# Columns a file must have to be usable.
_REQUIRED = {"labels": ("product",), "clients": ("id", "name"), "client_labels": ("client_id", "product")}


def table_of(file_name: str) -> tuple[str, str] | None:
    """(table, "csv" or "json") from an export file name, or None."""
    m = _NAME.match(PurePosixPath(file_name.replace("\\", "/")).name.lower())
    return (m.group(1), m.group(2)) if m else None


def _files(uploads: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """The uploads with any zip unpacked."""
    out, total = [], 0
    for name, data in uploads:
        if name.lower().endswith(".zip"):
            try:
                z = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                raise validation(f"{PurePosixPath(name).name} is not a zip file RxLabel can read.") from None
            for info in z.infolist():
                if info.is_dir() or table_of(info.filename) is None:
                    continue
                total += info.file_size
                if total > MAX_BYTES:
                    raise validation("The export is too big to move in one go.")
                out.append((info.filename, z.read(info)))
        else:
            total += len(data)
            if total > MAX_BYTES:
                raise validation("The export is too big to move in one go.")
            out.append((name, data))
    return out


def _text(name: str, data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise validation(f"{PurePosixPath(name).name} is not a UTF-8 text file.") from None


def _csv_rows(table: str, name: str, text: str) -> list[dict]:
    rows = list(csv.reader(io.StringIO(text, newline="")))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    known = set(EXPORT_COLUMNS[table])
    if not set(header) <= known or not set(_REQUIRED[table]) <= set(header):
        raise validation(f"{PurePosixPath(name).name} has no column headers. Export it again with "
                         "\"Include column headers\" ticked.")
    out = []
    for r in rows[1:]:
        out.append({h: (r[i] if i < len(r) else "") for i, h in enumerate(header)})
    return out


def _json_rows(table: str, name: str, text: str) -> list[dict]:
    try:
        rows = json.loads(text)
    except ValueError:
        raise validation(f"{PurePosixPath(name).name} is not a valid JSON export.") from None
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise validation(f"{PurePosixPath(name).name} is not an RxLabel export.")
    if rows and not set(_REQUIRED[table]) <= set().union(*(r.keys() for r in rows)):
        raise validation(f"{PurePosixPath(name).name} is missing columns RxLabel needs.")
    return rows


def _str(v) -> str | None:
    """Text, or None for nothing (the export writes nothing as an empty cell or null)."""
    if v is None:
        return None
    s = v if isinstance(v, str) else str(v)
    return s if s != "" else None


def _int(v) -> int | None:
    if isinstance(v, bool):
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _flag(v) -> bool | None:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower() if v is not None else ""
    return {"1": True, "true": True, "0": False, "false": False}.get(s)


def _normalise(table: str, row: dict) -> dict:
    if table == "labels":
        return {"product": _str(row.get("product")), "instructions": _str(row.get("instructions")),
                "warning": _str(row.get("warning")), "is_custom": _flag(row.get("is_custom")),
                "seed_key": _str(row.get("seed_key"))}
    if table == "clients":
        return {"id": _int(row.get("id")), "name": _str(row.get("name")), "contact": _str(row.get("contact")),
                "email": _str(row.get("email")), "home_address": _str(row.get("home_address"))}
    return {"client_id": _int(row.get("client_id")), "product": _str(row.get("product")),
            "instructions": _str(row.get("instructions")), "warning": _str(row.get("warning"))}


def read_export(uploads: list[tuple[str, bytes]]) -> dict[str, list[dict]]:
    """{"labels": [...], "clients": [...], "client_labels": [...]} from the
    uploaded files (a table not given is an empty list). Raises VALIDATION
    with a message to show when the files can't be used."""
    tables: dict[str, list[dict]] = {t: [] for t in TABLES}
    seen: set[str] = set()
    for name, data in _files(uploads):
        found = table_of(name)
        if found is None:
            raise validation(f"{PurePosixPath(name.replace(chr(92), '/')).name} isn't an RxLabel export file "
                             "(labels, clients or client_labels, .csv or .json).")
        table, fmt = found
        if table == "queue":
            continue
        if table in seen:
            raise validation(f"There are two {table} files. Choose the files from one export.")
        seen.add(table)
        text = _text(name, data)
        rows = _json_rows(table, name, text) if fmt == "json" else _csv_rows(table, name, text)
        if len(rows) > MAX_ROWS:
            raise validation(f"{table} has more than {MAX_ROWS:,} rows: too many to move in one go.")
        tables[table] = [_normalise(table, r) for r in rows]
    if not any(tables.values()) and not seen:
        raise validation("No labels, clients or client labels found. Choose the export's zip or its files.")
    if tables["client_labels"] and "clients" not in seen:
        raise validation("Client labels need the clients file from the same export.")
    return tables
