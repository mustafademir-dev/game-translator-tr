"""Metni kutuya sığdırma: en büyük puntodan başla, satır kır, küçült;
alt sınırda da sığmıyorsa kutuyu aşağı doğru uzat."""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtGui import QFont, QFontMetrics

PADDING = 4


@dataclass
class FitResult:
    px: int
    lines: list[str]
    height: int          # gereken kutu yüksekliği (>= istenen yükseklik)
    line_height: int


def make_font(family: str, px: int, bold: bool = False) -> QFont:
    f = QFont(family)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def wrap(text: str, fm: QFontMetrics, width: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        cand = f"{cur} {word}" if cur else word
        if fm.horizontalAdvance(cand) <= width:
            cur = cand
            continue
        if cur:
            lines.append(cur)
            cur = ""
        # Tek başına sığmayan kelime karakter karakter bölünür.
        while fm.horizontalAdvance(word) > width and len(word) > 1:
            n = len(word) - 1
            while n > 1 and fm.horizontalAdvance(word[:n]) > width:
                n -= 1
            lines.append(word[:n])
            word = word[n:]
        cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def fit_text(text: str, w: int, h: int, family: str, max_px: int = 28, min_px: int = 12,
             bold: bool = False) -> FitResult:
    inner_w = max(1, w - 2 * PADDING)
    inner_h = max(1, h - 2 * PADDING)
    max_px = max(min_px, max_px)
    for px in range(max_px, min_px - 1, -1):
        fm = QFontMetrics(make_font(family, px, bold))
        lines = wrap(text, fm, inner_w)
        lh = fm.lineSpacing()
        if lh * len(lines) <= inner_h:
            return FitResult(px, lines, h, lh)
    fm = QFontMetrics(make_font(family, min_px, bold))
    lines = wrap(text, fm, inner_w)
    lh = fm.lineSpacing()
    return FitResult(min_px, lines, lh * len(lines) + 2 * PADDING, lh)
