"""Text layout for labels: how text wraps in a box and how small it must get
to fit (the desktop's label_fit.rs). Used by the image renderer, which
shrinks text to fit, and by the check before printing, which warns when text
would print too small. Same arithmetic as the desktop (f32), so the answers
match it exactly.
"""

from __future__ import annotations

from .fonts import Font, Scaled, f32

# Rust's char::is_whitespace (Unicode White_Space). Not str.isspace, which
# also counts U+001C..U+001F.
_WHITESPACE = frozenset(
    "\t\n\x0b\x0c\r \x85\xa0            "
    "    　"
)

# Space kept on each side of text that had to shrink to fit its box, so a long
# value doesn't run into a border drawn around the box.
SHRINK_MARGIN_MM = 0.5

BoxMm = tuple[float, float, float, float]  # x, y, width, height


def is_space(c: str) -> bool:
    return c in _WHITESPACE


def all_space(s: str) -> bool:
    return all(c in _WHITESPACE for c in s)


def rust_trim(s: str) -> str:
    start, end = 0, len(s)
    while start < end and s[start] in _WHITESPACE:
        start += 1
    while end > start and s[end - 1] in _WHITESPACE:
        end -= 1
    return s[start:end]


def rust_trim_end(s: str) -> str:
    end = len(s)
    while end > 0 and s[end - 1] in _WHITESPACE:
        end -= 1
    return s[:end]


def tokenize(text: str) -> list[str]:
    """Words and the spaces between them; every whitespace character is its own
    token, and '(' starts a new one."""
    tokens: list[str] = []
    current = ""
    for c in text:
        if c in _WHITESPACE:
            if current:
                tokens.append(current)
                current = ""
            tokens.append(c)
        elif c == "(":
            if current:
                tokens.append(current)
            current = c
        else:
            current += c
    if current:
        tokens.append(current)
    return tokens


class _Measure:
    """line_width, kept as running state so a line can be extended without
    measuring it again (same additions in the same order)."""

    __slots__ = ("width", "last")

    def __init__(self, width: float = 0.0, last: int | None = None):
        self.width, self.last = width, last

    def add(self, font: Scaled, text: str) -> "_Measure":
        width, last = self.width, self.last
        for c in text:
            gid = font.font.glyph_id(c)
            width = f32(width + font.h_advance(gid))
            if last is not None:
                width = f32(width + font.kern(last, gid))
            last = gid
        return _Measure(width, last)


def line_width(font: Scaled, text: str) -> float:
    """Width of `text` at the font's scale, with kerning."""
    return _Measure().add(font, text).width


def line_height(font: Scaled) -> float:
    return abs(f32(f32(font.ascent() - font.descent()) + font.line_gap()))


def wrap(font: Scaled, tokens: list[str], max_w: float) -> tuple[list[str], bool]:
    """Greedy word wrap to `max_w`: the lines, and whether every word fitted
    the width (False: a single word is wider than the box; wrapping stops)."""
    lines: list[str] = []
    current = ""
    measure = _Measure()
    fits_width = True
    for token in tokens:
        if not current and all_space(token):
            continue
        extended = measure.add(font, token)
        if extended.width <= max_w:
            current += token
            measure = extended
        elif all_space(token):
            if current:
                lines.append(current)
                current, measure = "", _Measure()
        elif not current:
            fits_width = False
            break
        else:
            lines.append(current)
            current, measure = token, _Measure().add(font, token)
    if current:
        trimmed = rust_trim_end(current)
        if trimmed:
            lines.append(trimmed)
    return lines, fits_width


def fits(font: Font, text: str, width_mm: float, height_mm: float, size_mm: float, wraps: bool) -> bool:
    """Whether `text` fits a width x height box at `size_mm`. Without `wraps`
    the text must fit on one line."""
    k = 100.0  # measure in 1/100 mm
    scaled = font.scaled(f32(size_mm * k))
    max_w = f32(width_mm * k)
    max_h = f32(height_mm * k)
    limit_h = f32(max_h * f32(1.05))
    text = rust_trim(text)
    if not text:
        return True
    if not wraps:
        return line_width(scaled, text) <= max_w and line_height(scaled) <= limit_h
    lines, fits_width = wrap(scaled, tokenize(text), max_w)
    # A little slack: one line set exactly to the box height is fine.
    return fits_width and f32(f32(len(lines)) * line_height(scaled)) <= limit_h


def shrink_margin(text: BoxMm, rects: list[BoxMm]) -> float:
    """SHRINK_MARGIN_MM (at most 5% of the width) when a rectangle's left or
    right side runs along the text box's side (a border drawn around it), else 0."""
    tx, ty, tw, th = text

    def near(a: float, b: float) -> bool:
        return abs(a - b) <= SHRINK_MARGIN_MM

    bordered = any(ry < ty + th and ry + rh > ty and (near(rx, tx) or near(rx + rw, tx + tw))
                   for rx, ry, rw, rh in rects)
    return min(SHRINK_MARGIN_MM, tw * 0.05) if bordered else 0.0


def fitting_size(font: Font, text: str, width_mm: float, height_mm: float, design_mm: float,
                 floor_mm: float, wraps: bool, margin_mm: float) -> float | None:
    """The largest size, from `design_mm` down in 0.1 mm steps, at which the
    text fits; None if it doesn't fit even at `floor_mm`. Smaller sizes keep
    `margin_mm` free on each side, as the image renderer does."""
    if fits(font, text, width_mm, height_mm, design_mm, wraps):
        return design_mm
    inner = width_mm - 2.0 * margin_mm
    size = design_mm - 0.1
    while size + 1e-9 >= floor_mm:
        if fits(font, text, inner, height_mm, size, wraps):
            return size
        size -= 0.1
    return None
