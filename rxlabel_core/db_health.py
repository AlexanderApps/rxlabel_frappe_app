"""The database health score (the desktop's db.rs get_health_score)."""

from __future__ import annotations


def health(diagnostics: dict, integrity_ok: bool) -> dict:
    """The database health score (db.rs get_health_score)."""
    score, recs = 0, []
    if integrity_ok:
        score += 50
    else:
        recs.append("CRITICAL: Database corruption detected.")
    size = diagnostics["file_size"]
    ratio = size["actual_data"] / size["total"] if size["total"] > 0 else 1.0
    score += int(ratio * 30)
    if size["unused"] > 10 * 1024 * 1024:
        recs.append("Run VACUUM to reclaim over 10MB of wasted space.")
    if diagnostics["software"]["journal_mode"] == "wal":
        score += 10
    else:
        recs.append("Enable WAL mode for better concurrency.")
    if diagnostics["software"]["foreign_keys"]:
        score += 10
    status = "Healthy" if score > 85 else "Degraded" if score > 60 else "Critical"
    return {"score": score, "status": status, "recommendations": recs}
