"""Satır bloklarını paragraf bloklarına birleştirme ve Japonca olmayanları atma."""
from __future__ import annotations

from ..translate.text import contains_japanese
from .base import TextBlock


def _overlap(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _can_join_horizontal(prev: TextBlock, line: TextBlock) -> bool:
    size = max(prev.h, 1)
    if not (0.6 <= line.h / size <= 1.6):
        return False
    gap = line.y - (prev.y + prev.h)
    if gap < -0.5 * size or gap > 1.0 * size:
        return False
    # Yatayda örtüşme ya da sol kenar hizası (paragrafın ilk satırı girintili olabilir).
    return (_overlap(prev.x, prev.x + prev.w, line.x, line.x + line.w) > 0
            or abs(prev.x - line.x) <= 2 * size)


def _can_join_vertical(prev: TextBlock, col: TextBlock) -> bool:
    # Dikey yazı sağdan sola okunur: sonraki sütun öncekinin solundadır.
    size = max(prev.w, 1)
    if not (0.6 <= col.w / size <= 1.6):
        return False
    gap = prev.x - (col.x + col.w)
    if gap < -0.5 * size or gap > 1.0 * size:
        return False
    return (_overlap(prev.y, prev.y + prev.h, col.y, col.y + col.h) > 0
            or abs(prev.y - col.y) <= 2 * size)


def _union(blocks: list[TextBlock], vertical: bool) -> TextBlock:
    x0 = min(b.x for b in blocks)
    y0 = min(b.y for b in blocks)
    x1 = max(b.x + b.w for b in blocks)
    y1 = max(b.y + b.h for b in blocks)
    return TextBlock("".join(b.text for b in blocks), x0, y0, x1 - x0, y1 - y0, vertical)


def _same_row(a: TextBlock, b: TextBlock) -> bool:
    """OCR motorları bir satırı (ör. 、 işaretinden) parçalara bölebilir."""
    size = max(min(a.h, b.h), 1)
    if _overlap(a.y, a.y + a.h, b.y, b.y + b.h) < 0.5 * size:
        return False
    gap = max(a.x, b.x) - min(a.x + a.w, b.x + b.w)
    return gap <= 2 * max(a.h, b.h)


def _join_rows(lines: list[TextBlock]) -> list[TextBlock]:
    rows: list[list[TextBlock]] = []
    for line in sorted(lines, key=lambda b: b.x):
        for r in rows:
            if _same_row(r[-1], line):
                r.append(line)
                break
        else:
            rows.append([line])
    return [_union(r, False) for r in rows]


def merge_lines(lines: list[TextBlock]) -> list[TextBlock]:
    """Aynı paragrafa ait yakın satırları tek blokta birleştirir; Japonca içermeyenleri atar."""
    lines = [l for l in lines if l.text.strip()]
    horiz = _join_rows([l for l in lines if not l.vertical])
    lines = [l for l in horiz + [l for l in lines if l.vertical] if contains_japanese(l.text)]
    horiz = sorted((l for l in lines if not l.vertical), key=lambda b: (b.y, b.x))
    vert = sorted((l for l in lines if l.vertical), key=lambda b: (-(b.x + b.w), b.y))

    out: list[TextBlock] = []
    for items, joinable in ((horiz, _can_join_horizontal), (vert, _can_join_vertical)):
        groups: list[list[TextBlock]] = []
        for line in items:
            for g in groups:
                if joinable(g[-1], line):
                    g.append(line)
                    break
            else:
                groups.append([line])
        out.extend(_union(g, joinable is _can_join_vertical) for g in groups)
    return out
