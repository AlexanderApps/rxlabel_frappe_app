"""Date and time display formats (the frontend's utils/dateFormats.ts). The
setting stores the format's id; the browser does the formatting."""

from __future__ import annotations

from .errors import validation

DATE_FORMAT_IDS = ("d1", "d2", "d3", "d4", "d5", "dt1", "dt2", "dt3", "dt4", "dt5")
# "ISO Style": 2026-11-06 16:05
DEFAULT_DATE_FORMAT = "dt5"


def or_default(value: object) -> str:
    """A known format id, else the default (setup, older databases)."""
    return value if isinstance(value, str) and value in DATE_FORMAT_IDS else DEFAULT_DATE_FORMAT


def check(value: object) -> str | None:
    """For saving settings: None keeps the current format; anything else must be known."""
    if value is None:
        return None
    if value not in DATE_FORMAT_IDS:
        raise validation("Unknown date format.")
    return value  # type: ignore[return-value]
