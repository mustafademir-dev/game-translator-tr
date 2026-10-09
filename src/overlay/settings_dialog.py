"""Ayarlar penceresi (Ctrl+Alt+S): yazı tipi, punto, renk, kutu saydamlığı ve davranış.

Görünüm ayarları değiştikçe ekrandaki çeviri kutularına anında uygulanır; "İptal" eski
haline döndürür, "Kaydet" settings.json'a yazar.
"""
from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFontComboBox, QFormLayout,
                             QGroupBox, QLabel, QSlider, QSpinBox, QVBoxLayout, QWidget)

from .. import winapi
from .fit import PADDING, fit_text, make_font

# settings.json anahtarları ve varsayılanları (config.DEFAULTS ile aynı)
STYLE_KEYS = {
    "font_family": "",          # "" = uygulamayla gelen Noto Sans
    "font_max_px": 28,
    "font_min_px": 12,
    "font_bold": False,
    "text_color": "auto",
    "box_opacity": 100,
    "follow_original": True,
    "clear_on_click": True,
    "region_single_block": True,
    "ja_model": "sugoi",
}
TEXT_COLORS = [("auto", "Otomatik (arka plana göre)"), ("white", "Beyaz"), ("black", "Siyah")]
JA_MODELS = [("sugoi", "Sugoi + opus (doğru ve hızlı)"), ("nllb", "NLLB (eski)")]
SAMPLE = "Tanaka-san, bugün okula gelmiyor musun? Öğretmen seni soruyordu."


class _Preview(QWidget):
    """Sahte oyun arka planı üstünde örnek çeviri kutusu."""

    def __init__(self, dialog: "SettingsDialog"):
        super().__init__()
        self.dialog = dialog
        self.setMinimumHeight(130)

    def paintEvent(self, _):
        v = self.dialog.values()
        family = v["font_family"] or self.dialog.bundled_family
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0, QColor(70, 110, 160))
        g.setColorAt(1, QColor(190, 140, 90))
        p.fillRect(self.rect(), g)
        box = QRect(16, 20, self.width() - 32, 64)
        fit = fit_text(SAMPLE, box.width(), box.height(), family, v["font_max_px"], v["font_min_px"], v["font_bold"])
        h = max(box.height(), fit.height)
        bg = (24, 24, 28)
        p.fillRect(box.x(), box.y(), box.width(), h, QColor(*bg, round(2.55 * v["box_opacity"])))
        fg = {"white": (255, 255, 255), "black": (0, 0, 0)}.get(v["text_color"], (255, 255, 255))
        p.setPen(QColor(*fg))
        p.setFont(make_font(family, fit.px, v["font_bold"]))
        y = box.y() + max(PADDING, (h - fit.line_height * len(fit.lines)) // 2)
        for line in fit.lines:
            p.drawText(QRect(box.x() + PADDING, y, box.width() - 2 * PADDING, fit.line_height),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
            y += fit.line_height
        p.end()


class SettingsDialog(QDialog):
    def __init__(self, current: dict, bundled_family: str, on_change=None):
        """`current`: STYLE_KEYS değerleri. `on_change(values)`: her değişiklikte (canlı önizleme)."""
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Çeviri Ayarları")
        self.bundled_family = bundled_family
        self.original = {k: current.get(k, d) for k, d in STYLE_KEYS.items()}
        self.on_change = on_change
        self._loading = True

        lay = QVBoxLayout(self)
        look = QGroupBox("Görünüm")
        form = QFormLayout(look)
        self.font = QFontComboBox()
        self.font.setWritingSystem(QFontComboBox().writingSystem())  # tümü
        form.addRow("Yazı tipi:", self.font)
        self.max_px = QSpinBox(minimum=10, maximum=72, suffix=" px")
        form.addRow("En büyük punto:", self.max_px)
        self.min_px = QSpinBox(minimum=8, maximum=40, suffix=" px")
        form.addRow("En küçük punto:", self.min_px)
        self.bold = QCheckBox("Kalın yazı")
        form.addRow("", self.bold)
        self.color = QComboBox()
        for key, label in TEXT_COLORS:
            self.color.addItem(label, key)
        form.addRow("Yazı rengi:", self.color)
        self.opacity = QSlider(Qt.Orientation.Horizontal, minimum=30, maximum=100)
        self.opacity_label = QLabel()
        form.addRow("Kutu opaklığı:", self.opacity)
        form.addRow("", self.opacity_label)
        self.follow = QCheckBox("Serbest modda yazıyı orijinal yazıdan büyük yapma")
        form.addRow("", self.follow)
        lay.addWidget(look)

        self.preview = _Preview(self)
        lay.addWidget(self.preview)

        behave = QGroupBox("Davranış")
        form2 = QFormLayout(behave)
        self.clear_on_click = QCheckBox("Oyuna tıklayınca / Enter / Boşluk'ta çeviriyi sil")
        form2.addRow("", self.clear_on_click)
        self.single_block = QCheckBox("Tarama alanı sınırlıyken (Ctrl+Alt+E) alandaki yazıyı tek parça çevir")
        form2.addRow("", self.single_block)
        self.ja_model = QComboBox()
        for key, label in JA_MODELS:
            self.ja_model.addItem(label, key)
        form2.addRow("Japonca çeviri:", self.ja_model)
        form2.addRow("", QLabel("<i>Japonca çeviri yöntemi uygulama yeniden açılınca geçerli olur.</i>"))
        lay.addWidget(behave)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
                              | QDialogButtonBox.StandardButton.RestoreDefaults)
        bb.button(QDialogButtonBox.StandardButton.Save).setText("Kaydet")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("İptal")
        bb.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText("Varsayılanlar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            lambda: self.load(STYLE_KEYS))
        lay.addWidget(bb)

        for sig in (self.font.currentFontChanged, self.max_px.valueChanged, self.min_px.valueChanged,
                    self.bold.toggled, self.color.currentIndexChanged, self.opacity.valueChanged,
                    self.follow.toggled, self.clear_on_click.toggled, self.single_block.toggled,
                    self.ja_model.currentIndexChanged):
            sig.connect(self._changed)
        self.load(self.original)
        self.resize(480, 620)

    def load(self, v: dict) -> None:
        self._loading = True
        self.font.setCurrentFont(QFont(v["font_family"] or self.bundled_family))
        self.max_px.setValue(v["font_max_px"])
        self.min_px.setValue(v["font_min_px"])
        self.bold.setChecked(v["font_bold"])
        self.color.setCurrentIndex(max(0, self.color.findData(v["text_color"])))
        self.opacity.setValue(v["box_opacity"])
        self.follow.setChecked(v["follow_original"])
        self.clear_on_click.setChecked(v["clear_on_click"])
        self.single_block.setChecked(v["region_single_block"])
        self.ja_model.setCurrentIndex(max(0, self.ja_model.findData(v["ja_model"])))
        self._loading = False
        self._changed()

    def values(self) -> dict:
        family = self.font.currentFont().family()
        return {
            "font_family": "" if family == self.bundled_family else family,
            "font_max_px": max(self.max_px.value(), self.min_px.value()),
            "font_min_px": min(self.max_px.value(), self.min_px.value()),
            "font_bold": self.bold.isChecked(),
            "text_color": self.color.currentData(),
            "box_opacity": self.opacity.value(),
            "follow_original": self.follow.isChecked(),
            "clear_on_click": self.clear_on_click.isChecked(),
            "region_single_block": self.single_block.isChecked(),
            "ja_model": self.ja_model.currentData(),
        }

    def _changed(self, *_):
        if self._loading:
            return
        self.opacity_label.setText(f"%{self.opacity.value()}"
                                   + ("  (arkadaki orijinal yazı görünebilir)" if self.opacity.value() < 100 else ""))
        self.preview.update()
        if self.on_change:
            self.on_change(self.values())

    def showEvent(self, e):
        super().showEvent(e)
        winapi.exclude_from_capture(int(self.winId()))  # OCR bu pencereyi okumasın

    def reject(self):
        if self.on_change:
            self.on_change(self.original)  # canlı değişiklikleri geri al
        super().reject()
