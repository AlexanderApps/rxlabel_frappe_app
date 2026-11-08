"""How each field of a label fits its box, and which are too long to print
at a readable size (the desktop's print_doc_generator.rs fit_report /
too_long and job_pages_templates.rs readable_floor). Measured with the label
fonts, by the same rules as the image renderer: the printer shrinks text to
fit in both print modes.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import fonts, label_fit, label_jobs

# The fields checked for fit, in report order.
CHECKED_FIELDS = ("product", "instructions", "warning", "client")
# Fixed text (no placeholder) may shrink this far to fit its box.
FIXED_TEXT_MIN_MM = 1.0


def readable_for(field: str, settings: Mapping[str, Any]) -> float:
    if field in ("product", "instructions"):
        return float(settings["readable_main_mm"])
    return float(settings["readable_other_mm"])


def readable_floor(raw_text: str, design: float, settings: Mapping[str, Any]) -> float:
    """Smallest font height for a text element whose template text is
    `raw_text`: the readable size for the values it shows (the larger if
    several), 1 mm for fixed text; never above `design`."""
    if "{{" not in raw_text:
        floor = FIXED_TEXT_MIN_MM
    else:
        floor = float(settings["readable_other_mm"])
        for f in CHECKED_FIELDS:
            if "{{" + f + "}}" in raw_text:
                floor = max(floor, readable_for(f, settings))
    return min(floor, design)


def fill(text: str, values: Mapping[str, str]) -> str:
    """Replace every {{key}} with its value; missing keys print as nothing."""
    out, rest = [], text
    while (start := rest.find("{{")) >= 0:
        end = rest.find("}}", start + 2)
        if end < 0:
            break
        out.append(rest[:start])
        out.append(values.get(label_fit.rust_trim(rest[start + 2:end]), ""))
        rest = rest[end + 2:]
    out.append(rest)
    return "".join(out)


def _bounds(el: Mapping[str, Any]) -> label_fit.BoxMm:
    return (float(el.get("x") or 0.0), float(el.get("y") or 0.0),
            float(el.get("width") or 0.0), float(el.get("height") or 0.0))


def text_rules(el: Mapping[str, Any], settings: Mapping[str, Any] | None, raw_text: str) -> tuple[float, float, bool]:
    """(design size, smallest size, wraps) for a normalised text element, as
    the image renderer applies them (label_builder::Fit)."""
    design = float(el.get("fontHeight") or 2.0)
    wraps_by_template = el.get("autoReturn", 0) not in (0, None)
    fit = el.get("fit") or "shrink"
    if fit == "wrap":
        return design, design, True
    if fit == "clip":
        return design, design, False
    floor = el.get("minFontHeight")
    if floor is None:
        floor = readable_floor(raw_text, design, settings) if settings is not None else 1.0
    return design, min(float(floor), design), wraps_by_template


def fit_report(template: str, values: Mapping[str, str], settings: Mapping[str, Any]) -> list[dict]:
    """For each checked field on `template`: its design size, the smallest it
    may print, and the size it prints at (None: too long even at the smallest,
    and cut off in image printing)."""
    raw = label_jobs.templates().get(template)
    if raw is None:
        return []
    page = [label_jobs.normalise_element(el) for el in raw["jobPages"][0]]
    rects = [_bounds(el) for el in page if el["type"].lower() == "rectangle"]
    out: list[dict] = []
    for el in page:
        if el["type"].lower() != "text":
            continue
        box = _bounds(el)
        if box[2] <= 0 or box[3] <= 0:
            continue
        for field in CHECKED_FIELDS:
            if any(f["field"] == field for f in out) or "{{" + field + "}}" not in el["text"]:
                continue
            text = fill(el["text"], values)
            if not label_fit.rust_trim(text):
                continue
            design, floor, wraps = text_rules(el, settings, el["text"])
            font = fonts.get_font(el.get("fontName"), el.get("fontStyle"))
            margin = label_fit.shrink_margin(box, rects)
            out.append({"field": field, "design_mm": design, "floor_mm": floor,
                        "size_mm": label_fit.fitting_size(font, text, box[2], box[3], design, floor, wraps, margin)})
    return out


def too_long(template: str, values: Mapping[str, str], settings: Mapping[str, Any]) -> list[str]:
    return [f["field"] for f in fit_report(template, values, settings) if f["size_mm"] is None]
