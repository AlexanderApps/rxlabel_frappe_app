"""Label settings and calibration as saved (label_settings.rs, calibration.rs),
and which templates fit them."""

from __future__ import annotations

from typing import Any

from . import label_jobs

DEFAULT_LABEL_SETTINGS = {
    "width_mm": 48.0, "height_mm": 54.0, "readable_main_mm": 3.0, "readable_other_mm": 2.0,
    "double_print_minutes": 10, "client_label": "Client:", "dispensed_by_label": "Disp by:",
}
DEFAULT_CALIBRATION = {"offset_x": 0.0, "offset_y": 0.0, "rotation": 0, "threshold": 257}
DOUBLE_PRINT_CHOICES = (0, 5, 10, 15, 30, 60)
READABLE_RANGE = (1.5, 5.0)
MAX_WORDING_CHARS = 20
MAX_OFFSET_MM = 3.0


def label_settings_from_saved(saved: Any) -> dict:
    """Anything unreadable or invalid is the default (LabelSettings::from_saved)."""
    if not isinstance(saved, dict):
        return dict(DEFAULT_LABEL_SETTINGS)
    merged = {**DEFAULT_LABEL_SETTINGS, **saved}
    lo, hi = READABLE_RANGE
    try:
        ok = (all(lo <= float(merged[k]) <= hi for k in ("readable_main_mm", "readable_other_mm"))
              and merged["double_print_minutes"] in DOUBLE_PRINT_CHOICES
              and all(isinstance(merged[k], str) and len(merged[k]) <= MAX_WORDING_CHARS
                      for k in ("client_label", "dispensed_by_label"))
              and float(merged["width_mm"]) > 0 and float(merged["height_mm"]) > 0)
    except (TypeError, ValueError):
        ok = False
    return merged if ok else dict(DEFAULT_LABEL_SETTINGS)


def calibration_from_saved(saved: Any) -> dict:
    """Invalid values are the default (Calibration::from_saved)."""
    if not isinstance(saved, dict):
        return dict(DEFAULT_CALIBRATION)
    c = {**DEFAULT_CALIBRATION, **saved}
    try:
        ok = (all(abs(float(c[k])) <= MAX_OFFSET_MM + 1e-9 for k in ("offset_x", "offset_y"))
              and c["rotation"] in (0, 90, 180, 270) and 0 <= int(c["threshold"]) <= 257)
    except (TypeError, ValueError):
        ok = False
    return c if ok else dict(DEFAULT_CALIBRATION)


def template_size(name: str) -> tuple[float, float] | None:
    info = label_jobs.templates().get(name, {}).get("jobInfo", {})
    w, h = info.get("jobWidth"), info.get("jobHeight")
    return (float(w), float(h)) if w and h else None


def _same_size(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) < 0.01


def templates_for(settings: dict) -> list[str]:
    """Templates made for the settings' label size; all of them if none are."""
    names = list(label_jobs.templates())
    size = (float(settings["width_mm"]), float(settings["height_mm"]))
    fitting = [n for n in names if (s := template_size(n)) and _same_size(s, size)]
    return fitting or names


def label_sizes() -> list[dict]:
    """Every label size the templates use, with how many templates each."""
    sizes: list[dict] = []
    for name in label_jobs.templates():
        size = template_size(name)
        if size is None:
            continue
        for s in sizes:
            if _same_size((s["width_mm"], s["height_mm"]), size):
                s["templates"] += 1
                break
        else:
            sizes.append({"width_mm": size[0], "height_mm": size[1], "templates": 1})
    return sizes
