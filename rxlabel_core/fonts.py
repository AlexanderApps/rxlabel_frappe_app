"""The label fonts and their measurements (the desktop's font_loader.rs, and
the ab_glyph metrics it measures text with).

Templates name Arial. Liberation Sans (SIL Open Font License, same letter
widths and line height as Arial) is drawn in its place; the Arial files only
cover what Liberation Sans lacks, such as Arial Black. "Arial" maps to
Liberation Sans Bold, as image labels have always been bold.

Measurements follow ab_glyph exactly, so text wraps and shrinks where the
desktop's does: sizes are px of (ascent - descent), advances and kerning
(the `kern` table only) come from the font's design units, and arithmetic is
single precision (f32) like the Rust code.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

from fontTools.ttLib import TTFont

# Font name (as looked up) -> file in data/fonts.
EMBEDDED = {
    "Liberation Sans-Bold": "LiberationSans-Bold.ttf",
    "Liberation Sans-BoldItalic": "LiberationSans-BoldItalic.ttf",
    "Arial": "Arial-Bold.ttf",  # the desktop's assets/Arial.ttf is Arial Bold
    "Arial-Bold": "Arial-Bold.ttf",
    "Arial Black": "ArialBlack.ttf",
    "Arial Black-Bold": "ArialBlack.ttf",
}
# Open fonts drawn instead of a template's font name + style.
PREFERRED = {
    "Arial": "Liberation Sans-Bold",
    "Arial-Bold": "Liberation Sans-Bold",
    "Arial-Italic": "Liberation Sans-BoldItalic",
    "Arial-BoldItalic": "Liberation Sans-BoldItalic",
}
FALLBACK = "Liberation Sans-Bold"
LAST_RESORT = "Arial"

# fontStyle as numbers (label_jobs) and as template words.
_STYLE_SUFFIX = {1: "-Bold", 2: "-Italic", 3: "-BoldItalic",
                 "bold": "-Bold", "italic": "-Italic", "bolditalic": "-BoldItalic"}


def f32(x: float) -> float:
    """Round to single precision, as Rust's f32 arithmetic does."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


@dataclass
class Font:
    name: str
    file: str
    units_per_em: int
    ascent: float  # design units, as ttf-parser's ascender()/descender()/line_gap()
    descent: float
    line_gap: float
    advances: list[float]  # by glyph id
    cmap: dict[int, int]  # code point -> glyph id
    kerning: dict[tuple[int, int], float] = field(default_factory=dict)

    def glyph_id(self, ch: str) -> int:
        return self.cmap.get(ord(ch), 0)

    def scaled(self, size: float) -> "Scaled":
        return Scaled(self, f32(size))

    def path(self) -> str:
        return str(resources.files("rxlabel_core.data").joinpath("fonts", self.file))


class Scaled:
    """A font at a px size (ab_glyph PxScaleFont)."""

    def __init__(self, font: Font, size: float):
        self.font = font
        self.size = size
        height = f32(font.ascent - font.descent)
        self.factor = f32(size / height)

    def h_advance(self, gid: int) -> float:
        adv = self.font.advances[gid] if gid < len(self.font.advances) else 0.0
        return f32(self.factor * adv)

    def kern(self, first: int, second: int) -> float:
        return f32(self.factor * self.font.kerning.get((first, second), 0.0))

    def ascent(self) -> float:
        return f32(self.factor * self.font.ascent)

    def descent(self) -> float:
        return f32(self.factor * self.font.descent)

    def line_gap(self) -> float:
        return f32(self.factor * self.font.line_gap)


def _vertical_metrics(t: TTFont) -> tuple[int, int, int]:
    """ttf-parser's ascender(), descender(), line_gap()."""
    hhea, os2 = t["hhea"], t["OS/2"] if "OS/2" in t else None
    if os2 is not None and os2.fsSelection & (1 << 7):  # USE_TYPO_METRICS
        return os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap
    asc, desc, gap = hhea.ascent, hhea.descent, hhea.lineGap
    if asc == 0 and os2 is not None:
        asc = os2.sTypoAscender or os2.usWinAscent
    if desc == 0 and os2 is not None:
        desc = os2.sTypoDescender or -os2.usWinDescent
    if (hhea.ascent == 0 or hhea.descent == 0) and os2 is not None \
            and (os2.sTypoAscender != 0 or os2.sTypoDescender != 0):
        gap = os2.sTypoLineGap
    return asc, desc, gap


def _load(name: str, file: str) -> Font:
    with resources.files("rxlabel_core.data").joinpath("fonts", file).open("rb") as f:
        t = TTFont(f, lazy=True)
        order = t.getGlyphOrder()
        ids = {g: i for i, g in enumerate(order)}
        hmtx = t["hmtx"].metrics
        advances = [float(hmtx[g][0]) for g in order]
        cmap: dict[int, int] = {}
        # ttf-parser keeps the Unicode subtables in font order; the first that maps wins.
        for table in t["cmap"].tables:
            unicode = table.platformID == 0 or (table.platformID == 3 and table.platEncID in (1, 10))
            if not unicode or table.format == 14:
                continue
            for cp, glyph in table.cmap.items():
                cmap.setdefault(cp, ids[glyph])
        kerning: dict[tuple[int, int], float] = {}
        if "kern" in t:
            for st in t["kern"].kernTables:
                horizontal = getattr(st, "coverage", 1) & 1
                if getattr(st, "format", 0) != 0 or not horizontal:
                    continue
                for (a, b), v in st.kernTable.items():
                    kerning.setdefault((ids[a], ids[b]), float(v))
        asc, desc, gap = _vertical_metrics(t)
        return Font(name, file, t["head"].unitsPerEm, float(asc), float(desc), float(gap), advances, cmap, kerning)


@lru_cache(maxsize=None)
def _font(name: str) -> Font:
    return _load(name, EMBEDDED[name])


def variant_name(name: str | None, style) -> str:
    """The name looked up for a font name and style ("Arial" + bold -> "Arial-Bold")."""
    base = name or LAST_RESORT
    key = style.lower() if isinstance(style, str) else style
    suffix = _STYLE_SUFFIX.get(key, "")
    if not suffix or base.endswith(suffix):
        return base
    return base + suffix


def resolved_name(name: str | None, style=None) -> str:
    """The font drawn for a name and style: the open replacement, the font
    named, then the fallbacks."""
    requested = variant_name(name, style)
    for candidate in (PREFERRED.get(requested), requested, FALLBACK, LAST_RESORT):
        if candidate and candidate in EMBEDDED:
            return candidate
    return LAST_RESORT


def get_font(name: str | None, style=None) -> Font:
    return _font(resolved_name(name, style))
