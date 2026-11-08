"""Labels drawn as images (the desktop's label_image_builder.rs and the image
half of print_doc_generator.rs).

A label is drawn at 4x the printer's resolution in greyscale; the printer
SDK scales it to its dots and makes it black and white itself (that prints
sharper than sending dots). The preview reduces the same drawing to the
printer's dots and thresholds it, as the printer will.

Layout is the desktop's exactly (label_fit, the same sizes, wrapping,
shrinking and positions). Glyphs are rasterised unhinted by FreeType, with
exact area coverage like ab_glyph; shapes are drawn with ports of
imageproc's routines.
"""

from __future__ import annotations

import base64
import io
import math
import threading
from functools import lru_cache
from typing import Any, Mapping

from PIL import Image, ImageChops, ImageDraw

from . import fonts, label_checks, label_fit, label_jobs
from .fonts import f32

DEFAULT_DPI = 203
SUPER_SAMPLE = 4
AUTO_THRESHOLD = 257
# The SDK's "automatic" threshold, approximated for the preview: mid-grey.
AUTO_PREVIEW_THRESHOLD = 128
WARNING_SIGN = "⚠"

_ALIGN_CENTER, _ALIGN_END = 1, 2


def rust_round(x: float) -> int:
    """f32/f64::round: halves away from zero."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


class Raster:
    """Millimetres to pixels for one printer resolution."""

    def __init__(self, dpi: int):
        self.dots_per_mm = max(int(dpi), 1) / 25.4

    def px(self, mm: float) -> float:
        """Millimetres to 4x canvas pixels (as f32)."""
        return f32(mm * self.dots_per_mm * SUPER_SAMPLE)

    def snap(self, mm: float) -> float:
        return rust_round(mm * self.dots_per_mm) / self.dots_per_mm


# --- imageproc's drawing routines -------------------------------------------------

def _bresenham(start: tuple[float, float], end: tuple[float, float]):
    x0, y0 = start
    x1, y1 = end
    steep = abs(y1 - y0) > abs(x1 - x0)
    if steep:
        x0, y0, x1, y1 = y0, x0, y1, x1
    if x0 > x1:
        x0, x1, y0, y1 = x1, x0, y1, y0
    dx, dy = f32(x1 - x0), abs(f32(y1 - y0))
    x, y = int(x0), int(y0)
    error = f32(dx / 2)
    end_x = int(x1)
    step = 1 if y0 < y1 else -1
    while x <= end_x:
        yield (y, x) if steep else (x, y)
        x += 1
        error = f32(error - dy)
        if error < 0:
            y += step
            error = f32(error + dx)


def draw_line_segment(px, size: tuple[int, int], start, end, color: int) -> None:
    w, h = size
    for x, y in _bresenham(start, end):
        if 0 <= x < w and 0 <= y < h:
            px[x, y] = color


def draw_polygon(px, size: tuple[int, int], poly: list[tuple[int, int]], color: int) -> None:
    """Filled polygon and its outline (imageproc draw_polygon_mut)."""
    if not poly or poly[0] == poly[-1]:
        return
    w, h = size
    y_min = max(0, min(min(p[1] for p in poly), h - 1))
    y_max = max(0, min(max(p[1] for p in poly), h - 1))
    closed = poly + [poly[0]]
    edges = list(zip(closed, closed[1:]))
    for y in range(y_min, y_max + 1):
        hits: list[int] = []
        for (x0, y0), (x1, y1) in edges:
            if (y0 <= y <= y1) or (y1 <= y <= y0):
                if y0 == y1:
                    hits += [x0, x1]
                elif y0 == y or y1 == y:
                    if y1 > y:
                        hits.append(x0)
                    if y0 > y:
                        hits.append(x1)
                else:
                    fraction = f32((y - y0) / (y1 - y0))
                    hits.append(rust_round(f32(x0 + f32(fraction * (x1 - x0)))))
        hits.sort()
        for i in range(0, len(hits) - 1, 2):
            lo, hi = min(hits[i], w), min(hits[i + 1], w - 1)
            if lo < w and hi >= 0:
                for x in range(max(0, lo), max(0, hi) + 1):
                    px[x, y] = color
    for (x0, y0), (x1, y1) in edges:
        draw_line_segment(px, size, (float(x0), float(y0)), (float(x1), float(y1)), color)


def draw_filled_circle(px, size, center: tuple[int, int], radius: int, color: int) -> None:
    x, y, p = 0, radius, 1 - radius
    x0, y0 = center
    while x <= y:
        for (ax, ay), (bx, by) in (((x0 - x, y0 + y), (x0 + x, y0 + y)), ((x0 - y, y0 + x), (x0 + y, y0 + x)),
                                   ((x0 - x, y0 - y), (x0 + x, y0 - y)), ((x0 - y, y0 - x), (x0 + y, y0 - x))):
            draw_line_segment(px, size, (float(ax), float(ay)), (float(bx), float(by)), color)
        x += 1
        if p < 0:
            p += 2 * x + 1
        else:
            y -= 1
            p += 2 * (x - y) + 1


def draw_filled_rect(draw: ImageDraw.ImageDraw, size, x: int, y: int, w: int, h: int, color: int) -> None:
    cw, ch = size
    left, top = max(x, 0), max(y, 0)
    right, bottom = min(x + w, cw), min(y + h, ch)
    if right > left and bottom > top:
        draw.rectangle([left, top, right - 1, bottom - 1], fill=color)


def draw_thick_line(px, size, x1, y1, x2, y2, thickness: int, color: int) -> None:
    if thickness <= 1:
        draw_line_segment(px, size, (x1, y1), (x2, y2), color)
    elif abs(f32(y1 - y2)) < 0.5:
        # Horizontal: stacked one-pixel lines, thickness going down.
        for t in range(thickness):
            draw_line_segment(px, size, (x1, f32(y1 + t)), (x2, f32(y2 + t)), color)
    else:
        # A band `thickness` wide on the right of a downward line.
        dx, dy = f32(x2 - x1), f32(y2 - y1)
        length = f32(math.sqrt(f32(f32(dx * dx) + f32(dy * dy))))
        nx, ny = f32(-dy / length), f32(dx / length)
        if ny < 0 or (ny == 0 and nx < 0):
            nx, ny = -nx, -ny
        t = float(thickness)

        def pt(x: float, y: float) -> tuple[int, int]:
            return rust_round(x), rust_round(y)

        band = [pt(x1, y1), pt(x2, y2), pt(f32(x2 + f32(nx * t)), f32(y2 + f32(ny * t))),
                pt(f32(x1 + f32(nx * t)), f32(y1 + f32(ny * t)))]
        if band[0] != band[3] and band[1] != band[2]:
            draw_polygon(px, size, band, color)


def draw_warning_sign(canvas: Image.Image, area: tuple[float, float, float, float], height: float) -> None:
    """A warning triangle with "!" centred in `area`, at most `height` tall
    (the label fonts have no ⚠ glyph)."""
    x, y, w, h = area
    t = f32(min(height, h, f32(w * f32(0.866))) * f32(0.95))
    if t < 4.0:
        return
    side = f32(t / f32(0.866))
    cx, top = f32(x + f32(w / 2)), f32(y + f32(f32(h - t) / 2))
    corners = [(cx, top), (f32(cx + f32(side / 2)), f32(top + t)), (f32(cx - f32(side / 2)), f32(top + t))]
    px, size = canvas.load(), canvas.size
    draw_polygon(px, size, [(rust_round(a), rust_round(b)) for a, b in corners], 0)
    stroke = f32(t * f32(0.13))
    scale = f32(f32(f32(t / 3) - stroke) / f32(t / 3))
    centre = (cx, f32(top + f32(f32(t * 2) / 3)))
    inner = [(rust_round(f32(centre[0] + f32(f32(a - centre[0]) * scale))),
              rust_round(f32(centre[1] + f32(f32(b - centre[1]) * scale)))) for a, b in corners]
    draw_polygon(px, size, inner, 255)
    bar_w = max(f32(stroke * f32(0.9)), 1.0)
    draw_filled_rect(ImageDraw.Draw(canvas), size, rust_round(f32(cx - f32(bar_w / 2))),
                     rust_round(f32(top + f32(t * f32(0.36)))), rust_round(bar_w),
                     int(max(rust_round(f32(t * f32(0.32))), 1)), 0)
    draw_filled_circle(px, size, (rust_round(cx), rust_round(f32(top + f32(t * f32(0.8))))),
                       int(max(rust_round(f32(stroke * f32(0.55))), 1)), 0)


# --- text ------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _face(name: str):
    import freetype
    return freetype.Face(fonts._font(name).path())


@lru_cache(maxsize=None)
def _has_outline(name: str) -> frozenset[int]:
    """Glyph ids that draw something (imageproc skips the others when kerning)."""
    from fontTools.ttLib import TTFont
    with open(fonts._font(name).path(), "rb") as f:
        t = TTFont(f, lazy=True)
        glyf = t["glyf"]
        return frozenset(i for i, g in enumerate(t.getGlyphOrder()) if glyf[g].numberOfContours != 0)


def _draw_glyph(canvas: Image.Image, face, gid: int, x: float, y: float) -> None:
    """One glyph with its origin at (x, y), unhinted, exact area coverage
    (as ab_glyph rasterises), blended black over the canvas."""
    import freetype
    ix, iy = math.floor(x), math.floor(y)
    # Sub-pixel position: FreeType y points up.
    face.set_transform(freetype.Matrix(0x10000, 0, 0, 0x10000),
                       freetype.Vector(round((x - ix) * 64), round(-(y - iy) * 64)))
    face.load_glyph(gid, freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_NO_BITMAP | freetype.FT_LOAD_RENDER)
    slot = face.glyph
    bm = slot.bitmap
    if bm.width == 0 or bm.rows == 0:
        return
    if bm.pitch == bm.width:
        data = bytes(bm.buffer)
    else:
        data = b"".join(bytes(bm.buffer[r * bm.pitch:r * bm.pitch + bm.width]) for r in range(bm.rows))
    mask = Image.frombytes("L", (bm.width, bm.rows), data)
    left, top = ix + slot.bitmap_left, iy - slot.bitmap_top
    canvas.paste(0, (left, top, left + bm.width, top + bm.rows), mask)


def draw_text(canvas: Image.Image, x: int, y: int, size: float, font: fonts.Font, text: str) -> None:
    """Black text with its top-left at (x, y), laid out as imageproc's
    draw_text_mut: pen at the ascent, advances, and (quirk kept) kerning only
    between glyphs that have outlines."""
    scaled = font.scaled(size)
    ascent = scaled.ascent()
    face = _face(font.name)
    # ab_glyph's px size is ascent - descent; FreeType's is the em.
    face.set_char_size(round(scaled.size * font.units_per_em / (font.ascent - font.descent) * 64))
    outlined = _has_outline(font.name)
    w = 0.0
    last = None
    for ch in text:
        gid = font.glyph_id(ch)
        pen_x = w
        w = f32(w + scaled.h_advance(gid))
        if gid in outlined:
            if last is not None:
                w = f32(w + scaled.kern(gid, last))
            last = gid
            _draw_glyph(canvas, face, gid, x + pen_x, y + ascent)


def _text_element(canvas: Image.Image, el: Mapping[str, Any], r: Raster, rects: list) -> None:
    bx, by, bw, bh = (float(el.get(k) or 0.0) for k in ("x", "y", "width", "height"))
    x, y, max_w, max_h = r.px(bx), r.px(by), r.px(bw), r.px(bh)
    text = el.get("text", "")
    if label_fit.rust_trim(text) == WARNING_SIGN:
        draw_warning_sign(canvas, (x, y, max_w, max_h), r.px(float(el.get("fontHeight") or 4.0)))
        return
    font = fonts.get_font(el.get("fontName"), el.get("fontStyle"))
    # Templates get their floor from the label settings (minFontHeight); else 1 mm.
    design, floor_mm, wraps = label_checks.text_rules(el, None, text)
    tokens = label_fit.tokenize(text)

    def layout(size: float, width: float):
        scaled = font.scaled(size)
        if wraps:
            lines, fits_width = label_fit.wrap(scaled, tokens, width)
        else:
            line = label_fit.rust_trim(text)
            lines, fits_width = [line], label_fit.line_width(scaled, line) <= width
        lh = label_fit.line_height(scaled)
        return lines, lh, fits_width and f32(f32(len(lines)) * lh) <= max_h

    floor = max(r.px(floor_mm), 1.0)
    size = r.px(design)
    lines, lh, ok = layout(size, max_w)
    pad = 0.0
    if not ok and size > floor:
        pad = r.px(label_fit.shrink_margin((bx, by, bw, bh), rects))
    while not ok and size > floor:
        size = max(f32(size - 0.5), floor)
        lines, lh, ok = layout(size, f32(max_w - f32(2.0 * pad)))

    # Centred when it fits; otherwise from the top, cut off at the box.
    block = f32(f32(len(lines)) * lh)
    top = f32(f32(max_h - block) / 2) if block <= max_h else 0.0
    boxed = Image.new("L", (max(int(math.ceil(max_w)), 1), max(int(math.ceil(max_h)), 1)), 255)
    scaled = font.scaled(size)
    align = el.get("horizontalAlignment")
    for i, line in enumerate(lines):
        line_y = f32(top + f32(f32(i) * lh))
        if f32(line_y + lh) > f32(max_h + 0.5) and i > 0:
            break  # a line that would be cut in half is left out
        width = label_fit.line_width(scaled, line)
        if align == _ALIGN_CENTER:
            line_x = f32(f32(max_w - width) / 2)
        elif align == _ALIGN_END:
            line_x = f32(f32(max_w - width) - pad)
        else:
            line_x = pad
        draw_text(boxed, rust_round(max(line_x, 0.0)), rust_round(line_y), size, font, line)
    # Keep whichever pixel is darker, so text never erases lines under it.
    left, upper = rust_round(x), rust_round(y)
    region = (left, upper, left + boxed.width, upper + boxed.height)
    canvas.paste(ImageChops.darker(canvas.crop(region), boxed), region)


def _bounds(el: Mapping[str, Any]) -> tuple[float, float, float, float]:
    return tuple(float(el.get(k) or 0.0) for k in ("x", "y", "width", "height"))  # type: ignore[return-value]


_DRAWING = threading.Lock()


def render(job: Mapping[str, Any], dpi: int = DEFAULT_DPI) -> Image.Image:
    """The job's first page at 4x `dpi`, greyscale ("L"), as an image print
    sends it. One drawing at a time: the FreeType faces are shared."""
    with _DRAWING:
        return _render(job, dpi)


def _render(job: Mapping[str, Any], dpi: int) -> Image.Image:
    r = Raster(dpi)
    info = job["jobInfo"]
    w_mm, h_mm = float(info.get("jobWidth") or 48.0), float(info.get("jobHeight") or 54.0)
    size = (rust_round(w_mm * r.dots_per_mm) * SUPER_SAMPLE, rust_round(h_mm * r.dots_per_mm) * SUPER_SAMPLE)
    canvas = Image.new("L", size, 255)
    page = job["jobPages"][0]
    rects = [_bounds(el) for el in page if el["type"].lower() == "rectangle"]
    for el in page:
        kind = el["type"].lower()
        if kind == "rectangle":
            bx, by, bw, bh = _bounds(el)
            rx, ry = int(r.px(r.snap(bx))), int(r.px(r.snap(by)))
            rw, rh = max(int(r.px(bw)), 0), max(int(r.px(bh)), 0)
            line_mm = max(float(el.get("lineWidth") if el.get("lineWidth") is not None else 0.1), 0.5 / r.dots_per_mm)
            thick = max(int(r.px(line_mm)), 0)
            draw = ImageDraw.Draw(canvas)
            if el.get("fill"):
                draw_filled_rect(draw, size, rx, ry, rw, rh, 0)
            else:
                draw_filled_rect(draw, size, rx, ry, rw, thick, 0)
                draw_filled_rect(draw, size, rx, ry + rh - thick, rw, thick, 0)
                draw_filled_rect(draw, size, rx, ry, thick, rh, 0)
                draw_filled_rect(draw, size, rx + rw - thick, ry, thick, rh, 0)
        elif kind == "text":
            _text_element(canvas, el, r, rects)
        elif kind == "line":
            _line_element(canvas, el, r)
        # Barcodes, QR codes, images: not drawn (as on the desktop).
    return canvas


def _line_element(canvas: Image.Image, el: Mapping[str, Any], r: Raster) -> None:
    rx1 = float(el.get("x1") or 0.0)
    ry1 = float(el.get("y1") or 0.0)
    rx2 = float(el["x2"]) if el.get("x2") is not None else rx1
    ry2 = float(el["y2"]) if el.get("y2") is not None else ry1
    x1, y1, x2, y2 = r.px(rx1), r.px(ry1), r.px(rx2), r.px(ry2)
    orientation = el.get("orientation")
    if orientation == 90:
        x1, y1, x2, y2 = -y1, x1, -y2, x2
    elif orientation == 180:
        x1, y1, x2, y2 = -x1, -y1, -x2, -y2
    elif orientation == 270:
        x1, y1, x2, y2 = y1, -x1, y2, -x2
    thickness = rust_round(r.px(float(el.get("lineWidth") if el.get("lineWidth") is not None else 1.0)))
    px, size = canvas.load(), canvas.size
    dashes = el.get("dashLens") or []
    if not dashes:
        draw_thick_line(px, size, x1, y1, x2, y2, thickness, 0)
        return
    steps = [r.px(float(d)) for d in dashes]
    dx, dy = f32(x2 - x1), f32(y2 - y1)
    total = f32(math.sqrt(f32(f32(dx * dx) + f32(dy * dy))))
    if total <= 0:
        return
    ux, uy = f32(dx / total), f32(dy / total)
    dist, i, on = 0.0, 0, True
    while dist < total:
        nxt = min(f32(dist + steps[i % len(steps)]), total)
        if on:
            draw_thick_line(px, size, f32(x1 + f32(ux * dist)), f32(y1 + f32(uy * dist)),
                            f32(x1 + f32(ux * nxt)), f32(y1 + f32(uy * nxt)), thickness, 0)
        dist, i, on = nxt, i + 1, not on


# --- jobs ------------------------------------------------------------------------

def apply_label_settings(template: str, job: dict, settings: Mapping[str, Any]) -> None:
    """Wording and readable sizes from the label settings (apply_label_settings):
    each text element without its own minFontHeight gets the readable floor."""
    raw_page, page = label_jobs.templates()[template]["jobPages"][0], job["jobPages"][0]
    if len(raw_page) != len(page):
        return
    for raw, el in zip(raw_page, page):
        if raw.get("type") != "text":
            continue
        raw_text = raw.get("text", "")
        wording = label_jobs.wording_for(raw_text, settings)
        if wording is not None:
            el["text"] = wording
        if raw.get("minFontHeight") is None:
            design = float(raw.get("fontHeight") or 2.0)
            el["minFontHeight"] = label_checks.readable_floor(raw_text, design, settings)


def drawable_job(template: str, values: Mapping[str, str], settings: Mapping[str, Any]) -> dict:
    """A filled template with the label settings applied, ready to draw."""
    job = label_jobs.render(template, values)
    apply_label_settings(template, job, settings)
    return job


def png_bytes(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=False, compress_level=6)
    return out.getvalue()


def data_url(image: Image.Image) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes(image)).decode("ascii")


def image_job(image: Image.Image, width_mm: float, height_mm: float,
              calibration: Mapping[str, Any] | None = None) -> dict:
    """A print job holding one drawn label, for the print assistant: the image
    scaled to the label size, moved, rotated and made black and white as the
    calibration says (calibration.rs apply_to_image)."""
    cal = calibration or {}
    return {
        "printerInfo": {},
        "jobInfo": {"jobWidth": width_mm, "jobHeight": height_mm, "orientation": int(cal.get("rotation", 0) or 0)},
        "jobPages": [[{
            "type": "image", "imageFile": data_url(image),
            "x": label_jobs._round1(float(cal.get("offset_x", 0) or 0)),
            "y": label_jobs._round1(float(cal.get("offset_y", 0) or 0)),
            "width": width_mm, "height": height_mm,
            "threshold": int(cal.get("threshold", AUTO_THRESHOLD)),
        }]],
    }


def job_size(job: Mapping[str, Any]) -> tuple[float, float]:
    info = job["jobInfo"]
    return float(info.get("jobWidth") or 48.0), float(info.get("jobHeight") or 54.0)


def printer_dots(grey: Image.Image, dpi: int, width_mm: float, height_mm: float, threshold: int) -> Image.Image:
    """The 4x drawing reduced to the printer's dots (each block averaged) and
    made black and white the way the printer does: darker than `threshold`
    prints black (0-256; 257 automatic)."""
    def dots(mm: float) -> int:
        return max(rust_round(mm / 25.4 * dpi), 1)

    small = grey.resize((dots(width_mm), dots(height_mm)), Image.Resampling.BILINEAR)
    cut = AUTO_PREVIEW_THRESHOLD if threshold > 256 else threshold
    return small.point(lambda v: 0 if v < cut else 255)


def preview(template: str, values: Mapping[str, str], settings: Mapping[str, Any], dpi: int = DEFAULT_DPI,
            threshold: int = AUTO_THRESHOLD) -> dict:
    """The label exactly as an image print draws it, in the printer's dots,
    black and white; with the fit notes. Nothing is written or printed."""
    job = drawable_job(template, values, settings)
    w, h = job_size(job)
    image = printer_dots(render(job, dpi), dpi, w, h, threshold)
    return {"image": data_url(image), "width_mm": w, "height_mm": h, "dpi": dpi, "print_type": "image",
            "notes": label_checks.fit_report(template, values, settings)}


def build_image_jobs(template: str, labels: list[Mapping[str, str]], settings: Mapping[str, Any],
                     calibration: Mapping[str, Any] | None = None, dpi: int = DEFAULT_DPI) -> list[dict]:
    """Image printing: one job per printed copy, [{"label": index, "job": {...}}],
    each label drawn once. Fails as a whole if any label can't be prepared."""
    total = len(labels)
    out = []
    for i, label in enumerate(labels):
        values = {k: "" if v is None else str(v) for k, v in label.items()}
        label_jobs.fill_optional(values)
        which = "The label" if total == 1 else f"Label {i + 1} of {total}"
        try:
            job = drawable_job(template, values, settings)
        except label_jobs.TemplateError as e:
            raise label_jobs.TemplateError(f"{which} could not be prepared: {e}") from None
        w, h = job_size(job)
        printed = image_job(render(job, dpi), w, h, calibration)
        out.extend({"label": i, "job": printed} for _ in range(label_jobs.copies_of(values)))
    return out


def test_label_page(width_mm: float, height_mm: float, lines: list[str]) -> list[dict]:
    """The calibration label (Admin > Settings > Printing): a border just inside
    the label edge, centre marks, a title and `lines` of settings."""
    def text(value: str, y: float, height: float, size: float, bold: bool) -> dict:
        e: dict[str, Any] = {"type": "text", "text": value, "x": 2.0, "y": y, "width": width_mm - 4.0,
                             "height": height, "fontHeight": size, "fontName": "Arial",
                             "horizontalAlignment": "center", "verticalAlignment": "center"}
        if bold:
            e["fontStyle"] = "bold"
        if height > 3.0:
            e["autoReturn"] = "word"
        return e

    def bar(x: float, y: float, w: float, h: float) -> dict:
        return {"type": "rectangle", "x": x, "y": y, "width": w, "height": h, "fill": True}

    cx, cy = width_mm / 2.0, height_mm / 2.0
    page = [
        {"type": "rectangle", "x": 0.5, "y": 0.5, "width": width_mm - 1.0, "height": height_mm - 1.0,
         "lineWidth": 0.3},
        bar(cx - 3.0, cy - 0.15, 6.0, 0.3),
        bar(cx - 0.15, cy - 3.0, 0.3, 6.0),
        text("RxLabel test label", 2.0, 4.0, 3.2, True),
        text("The border should sit just inside the label edge on every side.", 6.5, 5.0, 2.0, False),
    ]
    page += [text(line, cy + 4.5 + i * 2.8, 2.6, 2.1, False) for i, line in enumerate(lines)]
    return [label_jobs.normalise_element(e) for e in page]


def test_label_lines(print_type: str, calibration: Mapping[str, Any], dpi: int, printer: str) -> list[str]:
    """What the test label says (print_test_label)."""
    def signed(v: float) -> str:
        return f"{v:+.1f} mm"

    lines = [f"Left/right: {signed(float(calibration.get('offset_x', 0)))}   "
             f"Up/down: {signed(float(calibration.get('offset_y', 0)))}",
             f"Rotation: {int(calibration.get('rotation', 0))}°"]
    if print_type == "image":
        t = int(calibration.get("threshold", AUTO_THRESHOLD))
        lines.append("Threshold: automatic" if t >= AUTO_THRESHOLD else f"Threshold: {t}")
    lines.append(f"{'Image' if print_type == 'image' else 'Text'} printing, {dpi} DPI")
    lines.append(printer)
    return lines


def test_label_job(print_type: str, lines: list[str], calibration: Mapping[str, Any] | None = None,
                   dpi: int = DEFAULT_DPI) -> dict:
    """The test label as a print job, on the default template's label size."""
    info = label_jobs.templates()[label_jobs.DEFAULT_TEMPLATE]["jobInfo"]
    w, h = float(info["jobWidth"]), float(info["jobHeight"])
    job = {"printerInfo": {}, "jobInfo": {"jobWidth": w, "jobHeight": h, "orientation": 0},
           "jobPages": [test_label_page(w, h, lines)]}
    if print_type == "image":
        return image_job(render(job, dpi), w, h, calibration)
    label_jobs.strip_image_only_fields(job)
    label_jobs.apply_calibration(job, calibration)
    return job
