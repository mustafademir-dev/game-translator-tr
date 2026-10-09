"""Resim modu: bilgisayardaki resimleri (tek resim ya da klasör) çevirip gösteren görüntüleyici.

- OCR ekrandan değil, resim dosyasının kendisinden, tam çözünürlükte yapılır; resmin her yerindeki
  farklı boyutlardaki yazılar ayrı ayrı bulunur ve üstlerine çevirileri çizilir.
- Gezinme: sol tık / → / Boşluk / tekerlek aşağı = sonraki; sağ tık / ← / tekerlek yukarı = önceki.
- Kullanıcı bir resme bakarken sıradaki resim arka planda çevrilir (önceden hazırlık).
- Gizlilik: görüntü, OCR metni ve çeviri yalnızca bellekte tutulur; diske hiçbir şey yazılmaz.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QRect, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from .capture import edge_color, text_color_for
from .config import Config
from .ocr import OcrUnavailableError, create_engine
from .overlay.fit import PADDING, fit_text, make_font
from .translate import LANGS, Dictionary

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
VERTICAL_MIN_W = 160     # dikey yazı bloklarında çeviri kutusunun en küçük ekran genişliği
CACHE_SIZE = 60          # bellekte tutulan çevrilmiş resim sayısı


def is_image(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in IMAGE_EXTS


def _natural_key(p: Path):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def list_images(paths: list[Path]) -> tuple[list[Path], int]:
    """Klasör -> içindeki resimler; tek resim -> bulunduğu klasördeki tüm resimler (o resimden
    başlayarak); birden çok resim -> yalnızca onlar. Doğal sıralama (2.png < 10.png)."""
    paths = [Path(p) for p in paths]
    if len(paths) == 1 and paths[0].is_dir():
        files = sorted((p for p in paths[0].iterdir() if is_image(p)), key=_natural_key)
        return files, 0
    if len(paths) == 1 and is_image(paths[0]):
        files = sorted((p for p in paths[0].parent.iterdir() if is_image(p)), key=_natural_key)
        return files, files.index(paths[0]) if paths[0] in files else 0
    files = sorted((p for p in paths if is_image(p)), key=_natural_key)
    return files, 0


def qimage_to_bgra(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format.Format_ARGB32)  # bellekte B, G, R, A
    h, w, bpl = img.height(), img.width(), img.bytesPerLine()
    arr = np.frombuffer(img.constBits().asstring(h * bpl), np.uint8).reshape(h, bpl)
    return arr[:, : w * 4].reshape(h, w, 4).copy()


@dataclass
class ImageItem:
    """Resim koordinatlarında bir yazı bloğu ve çevirisi."""
    x: int
    y: int
    w: int
    h: int
    text: str
    bg: tuple[int, int, int]
    fg: tuple[int, int, int]
    vertical: bool


class ImageWorker(QThread):
    """OCR + çeviri arka planda. İstenen resim önce, sonra sıradaki (önceden hazırlık)."""

    done = pyqtSignal(int, list, float)   # resim sırası, [ImageItem], süre (s)
    failed = pyqtSignal(int, str)         # resim sırası, hata (metin içeriği yok)
    error = pyqtSignal(str)               # genel hata bildirimi
    ready = pyqtSignal()

    def __init__(self, cfg: Config, lang: str, files: list[Path]):
        super().__init__()
        self.cfg, self.lang, self.files = cfg, lang, files
        self._cond = threading.Condition()
        self._wanted: list[int] = []
        self._done: set[int] = set()
        self._stop = False

    def focus(self, index: int) -> None:
        """Kullanıcı bu resme geçti: önce bu, sonra sıradaki ve bir sonraki."""
        n = len(self.files)
        with self._cond:
            self._wanted = [i for i in (index, index + 1, index + 2, index - 1) if 0 <= i < n]
            self._cond.notify()

    def forget(self, index: int) -> None:
        with self._cond:
            self._done.discard(index)

    def stop(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify()
        self.wait(10000)

    def _next_job(self) -> int | None:
        with self._cond:
            while not self._stop:
                job = next((i for i in self._wanted if i not in self._done), None)
                if job is not None:
                    self._done.add(job)
                    return job
                self._cond.wait()
            return None

    def run(self) -> None:
        try:
            self._run()
        except Exception as e:  # sessizce çökmesin; metin içeriği mesaja girmez
            import traceback
            traceback.print_exc()
            self.error.emit(f"Resim modu başlatılamadı: {type(e).__name__}: {e}"[:300])

    def _run(self) -> None:
        from .translate.factory import NoModelError, build_service
        try:
            service = build_service(self.cfg, self.lang, warn=self.error.emit)
        except NoModelError as e:
            self.error.emit(str(e))
            return
        dict_path = Config().path.parent / "dictionary.json"
        try:
            service.set_dictionary(Dictionary.load(dict_path))
        except (OSError, ValueError):
            self.error.emit("dictionary.json okunamadı (geçersiz JSON).")
        engine_name = self.cfg["image_ocr_engine"]
        if not engine_name:  # otomatik: Japonca resimde manga OCR (dikey yazı + furigana), yoksa genel ayar
            from .ocr.manga import manga_ocr_available
            engine_name = "manga" if self.lang == "ja" and manga_ocr_available() else self.cfg["ocr_engine"]
        try:
            engine = create_engine(engine_name, self.lang)
        except OcrUnavailableError:
            try:
                engine = create_engine("windows", self.lang)
            except OcrUnavailableError:
                self.error.emit(f"OCR kullanılamıyor: {LANGS[self.lang].name} dil paketi yok.")
                return
        self.ready.emit()
        while True:
            index = self._next_job()
            if index is None:
                return
            t0 = time.perf_counter()
            try:
                img = QImage(str(self.files[index]))
                if img.isNull():
                    self.failed.emit(index, "Resim açılamadı")
                    continue
                arr = qimage_to_bgra(img)
                items = []
                for b in engine.recognize(arr):
                    bg = edge_color(arr, b.x, b.y, b.w, b.h)
                    items.append(ImageItem(b.x, b.y, b.w, b.h, service.translate(b.text), bg,
                                           text_color_for(bg), b.vertical))
                self.done.emit(index, items, time.perf_counter() - t0)
            except Exception as e:  # metin içeriği mesaja girmez
                self.failed.emit(index, f"Hata: {type(e).__name__}")


class ImageViewer(QWidget):
    def __init__(self, cfg: Config, lang: str, files: list[Path], start: int, bundled_family: str, notify):
        super().__init__()
        self.cfg, self.lang, self.files = cfg, lang, files
        self.index = start
        self.bundled_family = bundled_family
        self.notify = notify
        self.results: dict[int, tuple[list[ImageItem], float] | str] = {}  # str = hata
        self.show_translation = True
        self.model_ready = False
        self.pixmap: QPixmap | None = None
        self.settings_dialog = None
        self.style_values = dict(cfg.data)
        self.setAcceptDrops(True)
        self.setMinimumSize(640, 480)
        self.setStyleSheet("background: #111;")
        self.worker = self._start_worker()
        self._load_current()
        self.resize(1200, 860)

    # --- iş parçacığı ---
    def _start_worker(self) -> ImageWorker:
        w = ImageWorker(self.cfg, self.lang, self.files)
        w.done.connect(self._on_done)
        w.failed.connect(self._on_failed)
        w.error.connect(lambda m: self.notify(m))
        w.ready.connect(self._on_ready)
        w.start()
        return w

    def _on_ready(self):
        self.model_ready = True
        self.update()

    def _on_done(self, index: int, items: list, seconds: float):
        self.results[index] = (items, seconds)
        if len(self.results) > CACHE_SIZE:  # en uzak resmin sonucunu unut
            far = max(self.results, key=lambda i: abs(i - self.index))
            del self.results[far]
            self.worker.forget(far)
        if index == self.index:
            self.update()

    def _on_failed(self, index: int, msg: str):
        self.results[index] = msg
        if index == self.index:
            self.update()

    # --- gezinme ---
    def _load_current(self):
        if not self.files:
            self.pixmap = None
            self.setWindowTitle("Resim Çevirisi")
            self.update()
            return
        path = self.files[self.index]
        self.pixmap = QPixmap(str(path))
        self.setWindowTitle(f"Resim Çevirisi - {path.name}")
        self.worker.focus(self.index)
        self.update()

    def go(self, delta: int):
        if not self.files:
            return
        new = max(0, min(len(self.files) - 1, self.index + delta))
        if new != self.index:
            self.index = new
            self._load_current()

    def open_paths(self, paths: list[Path]):
        files, start = list_images(paths)
        if not files:
            self.notify("Bu konumda resim bulunamadı.")
            return
        self.worker.stop()
        self.files, self.index, self.results = files, start, {}
        self.worker = self._start_worker()
        self._load_current()

    # --- girdi ---
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.go(+1)
        elif e.button() == Qt.MouseButton.RightButton:
            self.go(-1)

    def wheelEvent(self, e):
        self.go(+1 if e.angleDelta().y() < 0 else -1)

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key.Key_Right, Qt.Key.Key_Space, Qt.Key.Key_PageDown, Qt.Key.Key_Down):
            self.go(+1)
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Backspace, Qt.Key.Key_PageUp, Qt.Key.Key_Up):
            self.go(-1)
        elif k == Qt.Key.Key_Home:
            self.go(-len(self.files))
        elif k == Qt.Key.Key_End:
            self.go(len(self.files))
        elif k == Qt.Key.Key_O:
            self.show_translation = not self.show_translation
            self.update()
        elif k in (Qt.Key.Key_F, Qt.Key.Key_F11):
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif k == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
        elif k == Qt.Key.Key_S:
            self.open_settings()
        else:
            super().keyPressEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.open_paths([Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()])

    # --- ayarlar ---
    def open_settings(self):
        from .overlay.settings_dialog import STYLE_KEYS, SettingsDialog
        dlg = SettingsDialog({k: self.cfg[k] for k in STYLE_KEYS}, self.bundled_family,
                             on_change=self._apply_style)

        def save():
            self.cfg.data.update(dlg.values())
            self.cfg.save()
            self._apply_style(self.cfg.data)

        dlg.accepted.connect(save)
        self.settings_dialog = dlg
        dlg.show()

    def _apply_style(self, v: dict):
        self.style_values = dict(self.style_values, **v)
        self.update()

    def closeEvent(self, e):
        self.worker.stop()
        super().closeEvent(e)

    # --- çizim ---
    def _image_rect(self) -> QRect:
        if self.pixmap is None or self.pixmap.isNull():
            return QRect()
        area = self.rect().adjusted(0, 0, 0, -28)  # altta durum satırı
        pw, ph = self.pixmap.width(), self.pixmap.height()
        s = min(area.width() / pw, area.height() / ph)
        w, h = int(pw * s), int(ph * s)
        return QRect(area.x() + (area.width() - w) // 2, area.y() + (area.height() - h) // 2, w, h)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(17, 17, 17))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        v = self.style_values
        family = v["font_family"] or self.bundled_family
        r = self._image_rect()
        if self.pixmap is not None and not self.pixmap.isNull():
            p.drawPixmap(r, self.pixmap)
        result = self.results.get(self.index)
        if self.show_translation and isinstance(result, tuple) and self.pixmap is not None:
            s = r.width() / max(1, self.pixmap.width())
            for it in result[0]:
                x, y = r.x() + int(it.x * s), r.y() + int(it.y * s)
                w, h = max(1, int(it.w * s)), max(1, int(it.h * s))
                if it.vertical and w < VERTICAL_MIN_W:
                    x, w = max(r.x(), x + w // 2 - VERTICAL_MIN_W // 2), VERTICAL_MIN_W
                max_px = v["font_max_px"]
                if v["follow_original"] and not it.vertical:
                    max_px = max(v["font_min_px"], min(max_px, h - 2 * PADDING))
                fit = fit_text(it.text, w, h, family, max_px, v["font_min_px"], v["font_bold"])
                bh = max(h, fit.height)
                p.fillRect(x, y, w, bh, QColor(*it.bg, round(2.55 * v["box_opacity"])))
                fg = {"white": (255, 255, 255), "black": (0, 0, 0)}.get(v["text_color"], it.fg)
                p.setPen(QColor(*fg))
                p.setFont(make_font(family, fit.px, v["font_bold"]))
                ty = y + max(PADDING, (bh - fit.line_height * len(fit.lines)) // 2)
                for line in fit.lines:
                    p.drawText(QRect(x + PADDING, ty, w - 2 * PADDING, fit.line_height),
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
                    ty += fit.line_height
        # durum satırı
        p.setFont(make_font(self.bundled_family, 14))
        p.setPen(QColor(220, 220, 220))
        p.drawText(QRect(10, self.height() - 26, self.width() - 20, 24),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._status_text(result))
        p.end()

    def _status_text(self, result) -> str:
        if not self.files:
            return "Resim yok. Bir klasörü ya da resimleri bu pencereye sürükleyip bırakın."
        head = f"{self.index + 1}/{len(self.files)}  {self.files[self.index].name}  -  "
        if not self.model_ready:
            state = "çeviri modeli yükleniyor..."
        elif result is None:
            state = "çevriliyor..."
        elif isinstance(result, str):
            state = result
        elif not result[0]:
            state = f"{LANGS[self.lang].name} yazı bulunamadı"
        else:
            state = f"{len(result[0])} yazı çevrildi ({result[1]:.1f} s)"
            if not self.show_translation:
                state += "  [orijinal gösteriliyor]"
        keys = "   |   Sol tık / sağ ok: sonraki   Sağ tık / sol ok: önceki   O: orijinal   F: tam ekran   S: ayarlar"
        return head + state + keys
