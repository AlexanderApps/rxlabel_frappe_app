"""Label templates -> printer jobs for text ("json") printing.

A port of the desktop's src-tauri/src/job_pages_templates.rs (rendering,
validation), label_builder.rs (element serialisation: words such as
"center" or "bold" become the printer's numbers, notes are dropped),
print_doc_generator.rs (label-settings wording, RxLabel-only fields
removed) and printing/calibration.rs (apply_to_json).

Checked against the Rust code itself: tests/fixtures/rust_jobs.json is
produced by tools/rust_reference (see its README).
"""

from __future__ import annotations

import copy
import json
import math
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping

TEMPLATE_VARS = (
    "printer_model", "facility_name", "facility_address", "facility_contact",
    "product", "instructions", "warning", "client", "user_name", "timestamp",
)
REQUIRED_VARS = ("product", "instructions")
DEFAULT_TEMPLATE = "base"
MAX_COPIES = 20

ANNOTATION_KEYS = ("comment", "name")
IMAGE_ONLY_KEYS = ("fit", "minFontHeight")


class TemplateError(ValueError):
    """A label could not be prepared; the message is safe to show."""


# --- Element schema (label_builder.rs) ---------------------------------------

_ALIGNMENT = {"start": 0, "center": 1, "end": 2, "stretch": 3, "expand": 4}
_FONT_STYLE = {"regular": 0, "bold": 1, "italic": 2, "bolditalic": 3, "underline": 4, "strikeout": 8}
_AUTO_RETURN = {"none": 0, "char": 1, "word": 2}
_BARCODE = {"upc_a": 20, "upc_e": 21, "ean13": 22, "ean8": 23, "code39": 24, "itf25": 25, "codabar": 26,
            "code93": 27, "code128": 28, "isbn": 29, "eecode39": 30, "auto": 60}
_QR_ECC = {"l": 0, "m": 1, "q": 2, "h": 3}
_QR_ENCODING = {"unicode": 0, "ansi": 1, "utf8": 2}
_PDF417_ECC = {"auto": 0, **{f"l{i}": i for i in range(1, 9)}}
_FIT = ("shrink", "wrap", "clip")


def _enum(table: Mapping[str, int], normalise=str.lower):
    values = set(table.values())

    def convert(v: Any, key: str) -> int:
        if isinstance(v, str):
            n = table.get(normalise(v))
            if n is None:
                raise TemplateError(f"unknown {key} '{v}'")
            return n
        if isinstance(v, int) and not isinstance(v, bool) and v in values:
            return v
        raise TemplateError(f"invalid {key} value {v!r}")

    return convert


def _float(v: Any, key: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise TemplateError(f"{key} must be a number")
    return float(v)


def _uint(limit: int):
    def convert(v: Any, key: str) -> int:
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= limit:
            raise TemplateError(f"{key} must be a whole number")
        return v

    return convert


def _int(v: Any, key: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise TemplateError(f"{key} must be a whole number")
    return v


def _str(v: Any, key: str) -> str:
    if not isinstance(v, str):
        raise TemplateError(f"{key} must be text")
    return v


def _bool(v: Any, key: str) -> bool:
    if not isinstance(v, bool):
        raise TemplateError(f"{key} must be true or false")
    return v


def _orientation(v: Any, key: str) -> int:
    if isinstance(v, str):
        try:
            v = int(v.strip())
        except ValueError:
            raise TemplateError(f"invalid {key} '{v}'") from None
    if isinstance(v, bool) or v not in (0, 90, 180, 270):
        raise TemplateError(f"{key} must be 0, 90, 180 or 270")
    return v


def _line_space(v: Any, key: str) -> float:
    if isinstance(v, str):  # legacy "1_2" -> 1.2
        try:
            return float(v.replace("_", "."))
        except ValueError:
            raise TemplateError(f"invalid lineSpace '{v}'") from None
    return _float(v, key)


def _fit(v: Any, key: str) -> str:
    if v not in _FIT:
        raise TemplateError(f"unknown fit '{v}'")
    return v


def _floats(v: Any, key: str) -> list[float]:
    if not isinstance(v, list):
        raise TemplateError(f"{key} must be a list of numbers")
    return [_float(x, key) for x in v]


_ALIGN = _enum(_ALIGNMENT)
_BOUNDS = {"x": _float, "y": _float, "width": _float, "height": _float, "orientation": _orientation,
           "horizontalAlignment": _ALIGN, "verticalAlignment": _ALIGN}

# Fields per element type, in the order the desktop serialises them.
_ELEMENTS: dict[str, dict[str, Any]] = {
    "text": {"text": _str, **_BOUNDS, "fontName": _str, "fontHeight": _float, "fontStyle": _enum(_FONT_STYLE),
             "autoReturn": _enum(_AUTO_RETURN), "charSpace": _float, "lineSpace": _line_space,
             "leadingIndentChars": _int, "leadingIndentMm": _float, "leadingIndentColon": _bool,
             "fit": _fit, "minFontHeight": _float},
    "barcode": {"text": _str, "barcodeType": _enum(_BARCODE, lambda s: s.lower().replace("-", "_")), **_BOUNDS,
                "fontName": _str, "fontStyle": _enum(_FONT_STYLE), "textAlignment": _ALIGN,
                "textHeight": _float, "barPixels": _uint(255)},
    "qrcode": {"text": _str, **_BOUNDS, "textEncoding": _enum(_QR_ENCODING), "eccLevel": _enum(_QR_ECC),
               "qrcPixels": _uint(2**32 - 1)},
    "pdf417": {"text": _str, **_BOUNDS, "p417Pixels": _uint(2**32 - 1), "eccLevel": _enum(_PDF417_ECC)},
    "datamatrix": {"text": _str, **_BOUNDS},
    "image": {"imageFile": _str, **_BOUNDS, "threshold": _uint(2**32 - 1)},
    "rectangle": {**_BOUNDS, "lineWidth": _float, "cornerWidth": _float, "cornerHeight": _float, "fill": _bool},
    "ellipse": {**_BOUNDS, "lineWidth": _float, "fill": _bool},
    "line": {"x1": _float, "y1": _float, "x2": _float, "y2": _float, "lineWidth": _float,
             "dashLens": _floats, "orientation": _orientation},
}
_REQUIRED = {"text": ("text",), "barcode": ("text", "barcodeType"), "qrcode": ("text",), "pdf417": ("text",),
             "datamatrix": ("text",), "image": ("imageFile",)}


def _unknown_keys(element: dict) -> list[str]:
    fields = _ELEMENTS.get(str(element.get("type", "")).lower(), {})
    return [k for k in element if k != "type" and k not in fields and k not in ANNOTATION_KEYS]


def normalise_element(element: dict) -> dict:
    """One element as the desktop sends it: typed values, notes dropped, fixed key order."""
    if not isinstance(element, dict) or not isinstance(element.get("type"), str):
        raise TemplateError("element must be an object with a type")
    kind = element["type"].lower()
    fields = _ELEMENTS.get(kind)
    if fields is None:
        raise TemplateError(f"unknown element type '{element['type']}'")
    for key in _REQUIRED.get(kind, ()):
        if key not in element:
            raise TemplateError(f"{kind} element needs '{key}'")
    out: dict[str, Any] = {"type": element["type"]}
    for key, convert in fields.items():
        # Missing or null: left out (serde's skip_serializing_if = None).
        if element.get(key) is not None:
            out[key] = convert(element[key], key)
    _validate(kind, out)
    return out


def _validate(kind: str, el: dict) -> None:
    """build_job_pages' checks (validate_element)."""
    if kind == "text":
        if el.get("fontHeight", 1) <= 0:
            raise TemplateError("fontHeight must be positive")
        if el.get("charSpace", 0) < 0:
            raise TemplateError("charSpace cannot be negative")
    elif kind == "barcode":
        if el.get("textHeight", 0) < 0:
            raise TemplateError("textHeight cannot be negative")
        if "barPixels" in el and not 1 <= el["barPixels"] <= 7:
            raise TemplateError("barPixels must be between 1 and 7")
    elif kind == "image":
        t = el.get("threshold")
        if t is not None and t > 255 and t not in (256, 257):
            raise TemplateError("threshold must be 0-255, 256 or 257")
    if el.get("lineWidth", 0) < 0:
        raise TemplateError("lineWidth cannot be negative")


# --- Placeholders --------------------------------------------------------------

def _substitute(text: str, values: Mapping[str, str], missing: list[str]) -> str:
    """One left-to-right pass: inserted values are never scanned again."""
    out, rest = [], text
    while (start := rest.find("{{")) >= 0:
        end = rest.find("}}", start + 2)
        if end < 0:
            break
        out.append(rest[:start])
        key = rest[start + 2:end].strip()
        if key in values:
            out.append(values[key])
        else:
            missing.append(key)
            out.append(rest[start:end + 2])
        rest = rest[end + 2:]
    out.append(rest)
    return "".join(out)


def _substitute_tree(value: Any, values: Mapping[str, str], missing: list[str]) -> Any:
    if isinstance(value, str):
        return _substitute(value, values, missing) if "{{" in value else value
    if isinstance(value, list):
        return [_substitute_tree(v, values, missing) for v in value]
    if isinstance(value, dict):
        return {k: _substitute_tree(v, values, missing) for k, v in value.items()}
    return value


def _placeholders(text: str) -> list[str]:
    found: list[str] = []
    _substitute(text, {}, found)
    return found


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)


# --- Templates -----------------------------------------------------------------

def _check_template(t: Any) -> None:
    if not isinstance(t, dict) or set(t) != {"printerInfo", "jobInfo", "jobPages"}:
        raise TemplateError("needs exactly printerInfo, jobInfo and jobPages")
    if set(t["printerInfo"]) != {"printerName"}:
        raise TemplateError("printerInfo needs exactly printerName")
    info = t["jobInfo"]
    if set(info) != {"jobWidth", "jobHeight", "orientation"}:
        raise TemplateError("jobInfo needs exactly jobWidth, jobHeight and orientation")
    if not (_float(info["jobWidth"], "jobWidth") > 0 and _float(info["jobHeight"], "jobHeight") > 0):
        raise TemplateError("jobInfo jobWidth and jobHeight must be greater than 0")
    _orientation(info["orientation"], "orientation")
    unknown = sorted({k for s in _strings(t) for k in _placeholders(s) if k not in TEMPLATE_VARS})
    if unknown:
        raise TemplateError(f"unknown placeholder(s) {', '.join(unknown)}")
    pages = t["jobPages"]
    if not isinstance(pages, list) or not pages:
        raise TemplateError("jobPages must be a non-empty array of pages")
    for p, page in enumerate(pages, 1):
        if not isinstance(page, list) or not page:
            raise TemplateError(f"page {p} must be a non-empty array of elements")
        for i, el in enumerate(page, 1):
            bad = _unknown_keys(el) if isinstance(el, dict) else []
            if bad:
                raise TemplateError(f"page {p} element {i}: unknown field(s): {', '.join(bad)}")


@lru_cache(maxsize=1)
def templates() -> dict[str, dict]:
    """The templates, checked once (a bad one fails loudly, by name)."""
    text = resources.files("rxlabel_core.data").joinpath("job_pages_templates.json").read_text(encoding="utf-8")
    loaded = json.loads(text)
    problems = []
    if DEFAULT_TEMPLATE not in loaded:
        problems.append(f"the default template '{DEFAULT_TEMPLATE}' is missing")
    sample = {k: f"Sample {k}" for k in TEMPLATE_VARS}
    for name, t in loaded.items():
        try:
            _check_template(t)
            _render(t, name, sample)
        except TemplateError as e:
            problems.append(f"template '{name}': {e}")
    if problems:
        raise TemplateError("Invalid label templates:\n- " + "\n- ".join(problems))
    return dict(sorted(loaded.items()))


def _render(template: dict, name: str, values: Mapping[str, str]) -> dict:
    missing: list[str] = []
    job = _substitute_tree(copy.deepcopy(template), values, missing)
    if missing:
        raise TemplateError(f"Template '{name}' has unresolved placeholder(s): {', '.join(sorted(set(missing)))}")
    job["jobPages"] = [[normalise_element(el) for el in page] for page in job["jobPages"]]
    return job


def render(name: str, values: Mapping[str, str]) -> dict:
    """Fill a template; fails if any placeholder has no value."""
    all_templates = templates()
    if name not in all_templates:
        raise TemplateError(f"Template '{name}' not found. Available: {', '.join(all_templates)}")
    return _render(all_templates[name], name, values)


# --- Label settings and calibration ----------------------------------------------

def wording_for(fixed_text: str, settings: Mapping[str, Any]) -> str | None:
    return {"Client:": settings.get("client_label"), "Disp by:": settings.get("dispensed_by_label")}.get(fixed_text)


def apply_wording(name: str, job: dict, settings: Mapping[str, Any]) -> None:
    """Replace the templates' "Client:" / "Disp by:" with the label settings' wording."""
    raw_page, page = templates()[name]["jobPages"][0], job["jobPages"][0]
    if len(raw_page) != len(page):
        return
    for raw, el in zip(raw_page, page):
        if raw.get("type") == "text":
            wording = wording_for(raw.get("text", ""), settings)
            if wording is not None:
                el["text"] = wording


def strip_image_only_fields(job: dict) -> None:
    for page in job["jobPages"]:
        for el in page:
            for key in IMAGE_ONLY_KEYS:
                el.pop(key, None)


def _round1(v: float) -> float:
    """(v * 10).round() / 10 with Rust's f64::round: halves away from zero."""
    q = abs(v * 10)
    r = math.floor(q)
    if q - r >= 0.5:
        r += 1
    return math.copysign(r, v) / 10


def apply_calibration(job: dict, calibration: Mapping[str, Any] | None) -> None:
    """Rotate the job and move every element (never past the label's edge)."""
    cal = calibration or {}
    rotation = int(cal.get("rotation", 0) or 0)
    if rotation:
        job["jobInfo"]["orientation"] = rotation
    dx, dy = _round1(float(cal.get("offset_x", 0) or 0)), _round1(float(cal.get("offset_y", 0) or 0))
    if dx == 0 and dy == 0:
        return
    for page in job["jobPages"]:
        for el in page:
            for keys, d in ((("x", "x1", "x2"), dx), (("y", "y1", "y2"), dy)):
                for key in keys:
                    if isinstance(el.get(key), (int, float)) and not isinstance(el.get(key), bool):
                        el[key] = _round1(max(el[key] + d, 0.0))


# --- Jobs ------------------------------------------------------------------------

def fill_optional(values: dict[str, str]) -> None:
    """Absent optional values print blank; product and instructions are required."""
    for key in TEMPLATE_VARS:
        if key not in REQUIRED_VARS:
            values.setdefault(key, "")


def copies_of(values: Mapping[str, str]) -> int:
    try:
        n = int(str(values.get("copies", "1")).strip())
    except ValueError:
        n = 1
    return max(1, min(MAX_COPIES, n))


def json_job(name: str, values: Mapping[str, str], settings: Mapping[str, Any],
             calibration: Mapping[str, Any] | None = None) -> dict:
    """One label's text-printing job, as the desktop sends it to the printer."""
    job = render(name, values)
    apply_wording(name, job, settings)
    strip_image_only_fields(job)
    apply_calibration(job, calibration)
    return job


def build_jobs(name: str, labels: list[Mapping[str, str]], settings: Mapping[str, Any],
               calibration: Mapping[str, Any] | None = None) -> list[dict]:
    """One job per printed copy: [{"label": index, "job": {...}}]. Fails as a whole
    if any label can't be prepared, so a batch never prints with labels missing."""
    total = len(labels)
    out = []
    for i, label in enumerate(labels):
        values = {k: "" if v is None else str(v) for k, v in label.items()}
        fill_optional(values)
        try:
            job = json_job(name, values, settings, calibration)
        except TemplateError as e:
            which = "The label" if total == 1 else f"Label {i + 1} of {total}"
            raise TemplateError(f"{which} could not be prepared: {e}") from None
        out.extend({"label": i, "job": job} for _ in range(copies_of(values)))
    return out
