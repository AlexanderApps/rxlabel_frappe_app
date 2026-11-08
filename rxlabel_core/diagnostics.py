""""Export diagnostics": one zip a pharmacy can send to support (the
desktop's diagnostics.rs).

It holds summary.json (versions, licence status, database health, printer
status, counts and settings), the app's recent log files and a README. No
patient data: counts only, and any log line that mentions a product, client
or other personal value has that value replaced on the way out.
"""

from __future__ import annotations

import io
import json
import re
import zipfile

from .errors import validation

# Never more than this much log text in one bundle (newest first).
MAX_LOG_BYTES = 20 * 1024 * 1024

# `key=` values that may carry patient or personal data. Everything after
# such a key is dropped.
REDACT_KEYS = ("product", "instructions", "warning", "client", "name", "query", "email", "contact", "address")

_SECRET_WORDS = ("pass", "secret", "key", "token", "license")

README = (
    "RxLabel diagnostics\n"
    "\n"
    "summary.json   app and system versions, license status, database health,\n"
    "               printer status, record counts and settings\n"
    "logs/          the app's recent log files\n"
    "printing.txt   the browser's printing check, when it could run\n"
    "\n"
    "This bundle contains no labels, client details or passwords. Counts are\n"
    "included, contents are not. Log lines that mentioned products or names\n"
    "have those values replaced with [redacted].\n"
)


def redact_line(line: str) -> str:
    """Drop personal values from one log line (see REDACT_KEYS)."""
    cut: tuple[int, str] | None = None
    for key in REDACT_KEYS:
        # Whole key only: "file_name=" or "facility_name=" are fine.
        m = re.search(rf"(?<![A-Za-z0-9_]){key}=", line)
        if m and (cut is None or m.start() < cut[0]):
            cut = (m.start(), key)
    if cut is None:
        return line
    return f"{line[:cut[0]]}{cut[1]}=[redacted]"


def redact(text: str) -> str:
    return "\n".join(redact_line(line) for line in text.splitlines())


def safe_settings(settings: dict) -> dict:
    """Settings worth sending, minus anything that looks like a secret."""
    def secret(k: str) -> bool:
        return any(w in k.lower() for w in _SECRET_WORDS)
    return {k: ("[hidden]" if secret(k) else v) for k, v in settings.items()}


def build_zip(summary: dict, logs: list[tuple[str, str]], printing_report: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", README)
        z.writestr("summary.json", json.dumps(summary, indent=2, ensure_ascii=False))
        for name, text in logs:
            z.writestr(f"logs/{name}", text)
        if printing_report:
            z.writestr("printing.txt", redact(printing_report))
    return buffer.getvalue()


def optimization_metrics(before: int, after: int, before_readable: str, after_readable: str,
                         seconds: float) -> dict:
    """OptimizationMetrics as the desktop reports them (db.rs optimize_database)."""
    saved = before - after
    return {
        "duration_ms": int(seconds * 1000),
        "duration_sec": f"{seconds:.2f}s",
        "before_size": before_readable,
        "after_size": after_readable,
        "space_saved": f"{max(saved, 0) / (1024 * 1024):.2f} MB",
        "space_saved_bytes": saved,
        "compression_ratio": f"{max(saved, 0) / before * 100:.2f}%" if before > 0 else "0%",
    }


# Maintenance operations, in the order they run: check first, then rebuild,
# compact, and refresh statistics (MaintenanceOp::ORDER).
MAINTENANCE_ORDER = ("integrity", "reindex", "vacuum", "analyze")


def maintenance_ops(requested: object) -> list[str]:
    if not isinstance(requested, list) or not requested:
        raise validation("Choose at least one operation")
    unknown = [op for op in requested if op not in MAINTENANCE_ORDER]
    if unknown:
        raise validation(f"Unknown operation '{unknown[0]}'")
    return [op for op in MAINTENANCE_ORDER if op in requested]
