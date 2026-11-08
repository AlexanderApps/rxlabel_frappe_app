"""Checking values from the browser, with messages safe to show (they never
repeat what was typed: labels and client details stay out of errors and logs).

Frappe's own checks would repeat the value ("... (PARACETAMOL ...) will get
truncated"), so commands check first.
"""

from __future__ import annotations

from rxlabel_core.errors import AppError

SHORT = 140          # Data fields (varchar(140) on MariaDB)
LONG = 60_000        # Small Text fields (text, 64 KB)


def text(value, label: str, *, required: bool = False, max_len: int = SHORT) -> str | None:
    if value is None or (isinstance(value, str) and not required and value == ""):
        if required:
            raise AppError("VALIDATION", f"{label} is required.")
        return value
    if not isinstance(value, str):
        raise AppError("VALIDATION", f"{label} must be text.")
    if required and not value.strip():
        raise AppError("VALIDATION", f"{label} is required.")
    if len(value) > max_len:
        raise AppError("VALIDATION", f"{label} is too long (at most {max_len} characters).")
    return value


def long_text(value, label: str, *, required: bool = False) -> str | None:
    value = text(value, label, required=required, max_len=LONG)
    if isinstance(value, str) and len(value.encode("utf-8")) > LONG:
        raise AppError("VALIDATION", f"{label} is too long.")
    return value


def ident(value, label: str = "id") -> int:
    """A record id from the browser (a number, or digits)."""
    if isinstance(value, bool):
        raise AppError("VALIDATION", f"Invalid {label}.")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise AppError("VALIDATION", f"Invalid {label}.") from None


def flag(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


def stamp(value) -> str | None:
    """A date-time as the standalone app sends it: UTC, YYYY-MM-DD HH:MM:SS.
    Frappe keeps times in the site's time zone (System Settings)."""
    if value is None:
        return None
    import datetime
    from zoneinfo import ZoneInfo

    import frappe
    local = frappe.utils.get_datetime(value).replace(tzinfo=ZoneInfo(frappe.utils.get_system_timezone()))
    return local.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def number(value) -> int | None:
    """A link to a numbered record: MariaDB keeps links as text ("4"); the browser gets 4."""
    return None if value in (None, "") else int(value)
