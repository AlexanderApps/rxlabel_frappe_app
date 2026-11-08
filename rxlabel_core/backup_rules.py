"""Backup rules shared by every RxLabel backend (the desktop's backup.rs).

No files, database or clock here: the caller passes `now` and the backup
list, and does the I/O.
"""

from __future__ import annotations

import calendar
import math
from datetime import datetime, timedelta, timezone

from .errors import AppError, validation

MIN_PASSPHRASE_LEN = 12
MAX_PASSPHRASE_LEN = 256
MAX_BACKUPS_PER_TYPE = 50
PRE_RESTORE_KEEP = 3
FIRST_AUTO_BACKUP_DELAY = timedelta(minutes=2)

# Backup types as the frontend shows them (BackupType.ts).
AUTO, MANUAL, PRE_RESTORE = "Auto", "Manual", "PreRestore"
TYPES = (AUTO, MANUAL, PRE_RESTORE)
_NAME_KIND = {AUTO: "auto", MANUAL: "manual", PRE_RESTORE: "pre-restore"}

# How a backup file is encrypted (BackupEncryption.ts).
PASSPHRASE, LEGACY = "passphrase", "legacy"

FREQUENCIES = ("hourly", "daily", "weekly", "monthly")

# Tables a restore replaces, parents before children (db.rs RESTORE_TABLES).
RESTORE_TABLES = ("users", "settings", "labels", "clients", "client_labels", "queue")

# Every RxLabel database has these (verify_backup).
REQUIRED_TABLES = ("users", "settings", "labels")

WRONG_PASSPHRASE = "WRONG_PASSPHRASE"
PASSPHRASE_REQUIRED = "PASSPHRASE_REQUIRED"


def wrong_passphrase() -> AppError:
    return AppError(WRONG_PASSPHRASE, "That passphrase does not open this backup.")


def passphrase_required() -> AppError:
    return AppError(PASSPHRASE_REQUIRED, "This backup needs the passphrase it was made with.")


def validate_passphrase(passphrase: str) -> None:
    if len(passphrase.strip()) < MIN_PASSPHRASE_LEN:
        raise validation(f"Backup passphrase must be at least {MIN_PASSPHRASE_LEN} characters")
    if len(passphrase) > MAX_PASSPHRASE_LEN:
        raise validation("Backup passphrase is too long")


def parse_create_type(value: str) -> str:
    """`create_backup` takes "auto" or "manual" (a safety copy is never made on request)."""
    kinds = {"auto": AUTO, "manual": MANUAL}
    if value not in kinds:
        raise validation("Invalid backup type")
    return kinds[value]


def default_settings() -> dict:
    return {"auto": {"enabled": True, "frequency": "weekly", "max_count": 2, "last_run": None},
            "manual": {"max_count": 2}}


def clean_settings(new: object, last_run: str | None) -> dict:
    """Settings from the form, checked. `last_run` belongs to the scheduler, so
    the saved one is kept whatever the form sends."""
    try:
        auto, manual = new["auto"], new["manual"]  # type: ignore[index]
        enabled, frequency = auto["enabled"], auto["frequency"]
        counts = {"auto": auto["max_count"], "manual": manual["max_count"]}
    except (KeyError, TypeError):
        raise validation("Backup settings are incomplete.") from None
    if not isinstance(enabled, bool):
        raise validation("Backup settings are incomplete.")
    if frequency not in FREQUENCIES:
        raise validation("Unknown backup frequency.")
    for label, n in counts.items():
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_BACKUPS_PER_TYPE:
            raise validation(f"Keep between 1 and {MAX_BACKUPS_PER_TYPE} {label} backups")
    return {"auto": {"enabled": enabled, "frequency": frequency, "max_count": counts["auto"],
                     "last_run": last_run},
            "manual": {"max_count": counts["manual"]}}


def keep_count(settings: dict, backup_type: str) -> int:
    if backup_type == AUTO:
        return settings["auto"]["max_count"]
    if backup_type == MANUAL:
        return settings["manual"]["max_count"]
    return PRE_RESTORE_KEEP


def _add_month(t: datetime) -> datetime:
    # As chrono's `+ Months::new(1)`: the same day next month, or its last day.
    year, month = (t.year + 1, 1) if t.month == 12 else (t.year, t.month + 1)
    return t.replace(year=year, month=month, day=min(t.day, calendar.monthrange(year, month)[1]))


def next_run(frequency: str, after: datetime) -> datetime:
    """One period after `after` (get_next_run)."""
    if frequency == "hourly":
        return after + timedelta(hours=1)
    if frequency == "daily":
        return after + timedelta(days=1)
    if frequency == "weekly":
        return after + timedelta(weeks=1)
    return _add_month(after)


def next_auto_backup(settings: dict, meta: dict, started: datetime) -> datetime | None:
    """When the next automatic backup is due, or None when they're off: one
    period after the later of the last run and the newest automatic backup,
    or shortly after the schedule `started` (app start, or settings saved)
    when there has been none.

    (The desktop's next_auto_run counts that first delay from *now* each time
    it looks, so the first automatic backup keeps moving away; counting from
    the start makes it happen.)"""
    auto = settings["auto"]
    if not auto["enabled"]:
        return None
    times = [parse_time(m["created_at"]) for m in meta.values() if m["backup_type"] == AUTO]
    if auto.get("last_run"):
        times.append(parse_time(auto["last_run"]))
    times = [t for t in times if t is not None]
    if not times:
        return started + FIRST_AUTO_BACKUP_DELAY
    return next_run(auto["frequency"], max(times))


def parse_time(value: str) -> datetime | None:
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat()


def base_name(backup_type: str, now: datetime) -> str:
    """rxlabel-backup_2026-11-06T10-42-04.417_manual (generate_backup_name)."""
    ts = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.") + f"{now.microsecond // 1000:03d}"
    return f"rxlabel-backup_{ts}_{_NAME_KIND[backup_type]}"


def file_name(base: str, size_bytes: int) -> str:
    return f"{base}_{size_bytes // 1_000_000}MB.db"


def is_safe_name(name: str) -> bool:
    return bool(name) and "/" not in name and "\\" not in name and ".." not in name and "\0" not in name


def format_bytes(n: int) -> str:
    """'1.50 MB' (format_bytes)."""
    units = ["B", "KB", "MB", "GB"]
    i = 0 if n <= 0 else min(int(math.floor(math.log(n, 1024))), len(units) - 1)
    return f"{n / 1024 ** i:.2f} {units[i]}"


def over_limit(meta: dict, backup_type: str, limit: int) -> list[str]:
    """The oldest backups of `backup_type` beyond `limit` (enforce_retention)."""
    entries = sorted((m["created_at"], name) for name, m in meta.items() if m["backup_type"] == backup_type)
    excess = max(0, len(entries) - limit)
    return [name for _, name in entries[:excess]]


def backup_info(name: str, meta: dict, exists: bool) -> dict:
    return {"file_name": name, "backup_type": meta["backup_type"], "created_at": meta["created_at"],
            "size_bytes": meta["size_bytes"], "size_readable": format_bytes(meta["size_bytes"]),
            "exists_on_disk": exists, "encryption": meta.get("encryption", LEGACY)}

