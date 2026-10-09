"""Oyun penceresini kaplayan tek şeffaf overlay penceresi ve kısa bildirimler."""
from __future__ import annotations

import time
from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from .. import winapi
from .fit import PADDING, FitResult, fit_text, make_font

FIXED_BG = (24, 24, 28)
HANDLE = 14  # düzenleme modunda kenardan boyutlandırma alanı


@dataclass
class OverlayItem:
    x: int
    y: int
    w: int
    h: int
    text: str
    bg: tuple[int, int, int] = FIXED_BG
    fg: tuple[int, int, int] = (255, 255, 255)


class _NativeStyled(QWidget):
    """Üstte, çerçevesiz, odak almayan, tıklamayı geçiren ve yakalamadan hariç pencere."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._click_through = True

    def hwnd(self) -> int:
        return int(self.winId())

    def apply_native(self) -> None:
        winapi.exclude_from_capture(self.hwnd())
        winapi.set_click_through(self.hwnd(), self._click_through)

    def set_click_through(self, enabled: bool) -> None:
        self._click_through = enabled
        winapi.set_click_through(self.hwnd(), enabled)

    def showEvent(self, e):
        super().showEvent(e)
        self.apply_native()


class OverlayWindow(_NativeStyled):
    box_changed = pyqtSignal(list)      # [x, y, w, h] (sabit kutu)
    region_changed = pyqtSignal(object)  # [x, y, w, h] | None (serbest konum tarama alanı)
    painted = pyqtSignal(list, float)    # [(x, y, w, h)], çizim süresi ms

    def __init__(self, font_family: str, max_px: int = 28, min_px: int = 12):
        super().__init__()
        self.font_family = font_family
        self.max_px, self.min_px = max_px, min_px
        self.bold = False
        self.text_color = "auto"        # "auto" (arka plana göre) | "white" | "black"
        self.box_opacity = 100          # kutu opaklığı, %
        self.follow_original = True     # serbest mod: punto orijinal yazının boyunu geçmesin
        self.mode = "fixed"
        self.box: list[int] | None = None
        self.region: list[int] | None = None
        self.items: list[OverlayItem] = []
        self._layout: list[tuple[OverlayItem, FitResult]] = []
        self.edit = False
        self.debug_text: str | None = None
        self.last_draw_ms = 0.0
        self._drag: tuple[str, QPoint, list[int]] | None = None
        self._region_draft: QRect | None = None

    # --- durum ---
    def set_style(self, family: str, max_px: int, min_px: int, bold: bool, text_color: str,
                  box_opacity: int, follow_original: bool) -> None:
        """Ayarlar penceresinden: değişiklik ekrandaki kutulara anında uygulanır."""
        self.font_family, self.max_px, self.min_px = family, max_px, min_px
        self.bold, self.text_color, self.box_opacity = bold, text_color, box_opacity
        self.follow_original = follow_original
        self._relayout()

    def set_target_rect(self, x: int, y: int, w: int, h: int) -> None:
        if self.geometry() != QRect(x, y, w, h):
            self.setGeometry(x, y, w, h)
            self._relayout()

    def set_mode(self, mode: str, box: list[int] | None, region: list[int] | None) -> None:
        self.mode, self.box, self.region = mode, box, region
        self.items = []
        self._relayout()

    def default_box(self) -> list[int]:
        w, h = self.width(), self.height()
        return [int(w * 0.05), int(h * 0.72), int(w * 0.9), int(h * 0.24)]

    def set_items(self, items: list[OverlayItem]) -> None:
        self.items = items
        self._relayout()

    def set_fixed_text(self, text: str) -> None:
        box = self.box or self.default_box()
        self.set_items([OverlayItem(*box, text)] if text else [])

    def set_edit(self, on: bool) -> None:
        self.edit = on
        self.set_click_through(not on)
        if on:
            self.raise_()
        self.update()

    def set_debug(self, text: str | None) -> None:
        if text != self.debug_text:
            self.debug_text = text
            self.update()

    def _relayout(self) -> None:
        self._layout = []
        for it in self.items:
            if self.mode == "fixed":
                it.x, it.y, it.w, it.h = self.box or self.default_box()
            max_px = self.max_px
            if self.mode == "free" and self.follow_original:
                max_px = max(self.min_px, min(self.max_px, it.h - 2 * PADDING))
            self._layout.append((it, fit_text(it.text, it.w, it.h, self.font_family, max_px, self.min_px,
                                              self.bold)))
        self.update()

    # --- çizim ---
    def paintEvent(self, _):
        t0 = time.perf_counter()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if self.edit:
            p.fillRect(self.rect(), QColor(0, 120, 255, 40))  # alfa>0: fare olaylarını alır
            pen = QPen(QColor(0, 160, 255), 2, Qt.PenStyle.DashLine)
            p.setPen(pen)
            if self.mode == "fixed":
                b = self.box or self.default_box()
                p.drawRect(*b)
                p.fillRect(b[0] + b[2] - HANDLE, b[1] + b[3] - HANDLE, HANDLE, HANDLE, QColor(0, 160, 255))
            else:
                r = self._region_draft or (QRect(*self.region) if self.region else None)
                if r is not None:
                    p.drawRect(r)
            p.setFont(make_font(self.font_family, 16))
            p.setPen(QColor(255, 255, 255))
            hint = ("Düzenleme: kutuyu sürükle, sağ alt köşeden boyutlandır. Bitirince Ctrl+Alt+E"
                    if self.mode == "fixed" else
                    "Düzenleme: taranacak alanı sürükleyerek çiz, sağ tık = tüm pencere. Bitirince Ctrl+Alt+E")
            p.drawText(12, 26, hint)
        rects = []
        for it, fit in self._layout:
            h = max(it.h, fit.height)
            p.fillRect(it.x, it.y, it.w, h, QColor(*it.bg, round(2.55 * self.box_opacity)))
            p.setFont(make_font(self.font_family, fit.px, self.bold))
            fg = {"white": (255, 255, 255), "black": (0, 0, 0)}.get(self.text_color, it.fg)
            p.setPen(QColor(*fg))
            total = fit.line_height * len(fit.lines)
            y = it.y + max(PADDING, (h - total) // 2)
            for line in fit.lines:
                p.drawText(QRect(it.x + PADDING, y, it.w - 2 * PADDING, fit.line_height),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
                y += fit.line_height
            rects.append((it.x, it.y, it.w, h))
        if self.debug_text:
            p.setFont(make_font(self.font_family, 14))
            lines = self.debug_text.split("\n")
            top = 40  # sol üst, düzenleme ipucunun altında
            p.fillRect(4, top, 260, 22 * len(lines) + 8, QColor(0, 0, 0, 200))
            p.setPen(QColor(120, 255, 120))
            for i, line in enumerate(lines):
                p.drawText(10, top + 20 + 22 * i, line)
        p.end()
        self.last_draw_ms = (time.perf_counter() - t0) * 1000
        self.painted.emit(rects, self.last_draw_ms)

    # --- düzenleme modu fare olayları ---
    def mousePressEvent(self, e):
        if not self.edit:
            return
        pos = e.position().toPoint()
        if self.mode == "fixed":
            b = list(self.box or self.default_box())
            r = QRect(*b)
            if e.button() != Qt.MouseButton.LeftButton or not r.contains(pos):
                return
            corner = pos.x() >= r.right() - HANDLE and pos.y() >= r.bottom() - HANDLE
            self._drag = ("resize" if corner else "move", pos, b)
        else:
            if e.button() == Qt.MouseButton.RightButton:
                self.region = None
                self.region_changed.emit(None)
                self.update()
                return
            self._drag = ("region", pos, [])
            self._region_draft = QRect(pos, pos)

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        kind, start, b = self._drag
        pos = e.position().toPoint()
        d = pos - start
        if kind == "move":
            self.box = [b[0] + d.x(), b[1] + d.y(), b[2], b[3]]
        elif kind == "resize":
            self.box = [b[0], b[1], max(60, b[2] + d.x()), max(30, b[3] + d.y())]
        else:
            self._region_draft = QRect(start, pos).normalized()
        self._relayout()

    def mouseReleaseEvent(self, e):
        if not self._drag:
            return
        kind = self._drag[0]
        self._drag = None
        if kind == "region":
            r = self._region_draft
            self._region_draft = None
            if r is not None and r.width() > 20 and r.height() > 20:
                self.region = [r.x(), r.y(), r.width(), r.height()]
                self.region_changed.emit(self.region)
        else:
            self.box_changed.emit(list(self.box))
        self.update()


class Toast(_NativeStyled):
    """Ekranın üst ortasında birkaç saniye görünen kısa bildirim."""

    def __init__(self, font_family: str):
        super().__init__()
        self.font_family = font_family
        self.text = ""
        self._timer = QTimer(self, singleShot=True, timeout=self.hide)

    def show_message(self, text: str, seconds: float = 5.0) -> None:
        self.text = text
        font = make_font(self.font_family, 16)
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(font)
        lines = text.split("\n")
        w = max(fm.horizontalAdvance(l) for l in lines) + 32
        h = fm.lineSpacing() * len(lines) + 20
        scr = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(scr.x() + (scr.width() - w) // 2, scr.y() + 40, w, h)
        self.show()
        self.raise_()
        self.update()
        self._timer.start(int(seconds * 1000))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(40, 40, 48, 235))
        p.setPen(QColor(255, 190, 60))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)
        p.setFont(make_font(self.font_family, 16))
        p.setPen(QColor(255, 255, 255))
        p.drawText(self.rect().adjusted(16, 10, -16, -10), Qt.AlignmentFlag.AlignLeft, self.text)
        p.end()
