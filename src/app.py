"""Ana uygulama: pencere/mod seçimi, kısayollar, pano, overlay ve worker thread'i bağlar.

Çalıştırma:  venv\\Scripts\\python.exe -m src.app [--window BAŞLIK] [--mode fixed|free]
"""
from __future__ import annotations

from .app_env import setup_offline_env

setup_offline_env()

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import queue  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

from . import winapi  # noqa: E402

winapi.set_dpi_awareness()
# Tüm koordinatlar fiziksel piksel: Qt'nin kendi DPI ölçeklemesi kapalı.
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window=false")

from PyQt6.QtCore import QAbstractNativeEventFilter, QObject, QThread, QTimer, pyqtSignal  # noqa: E402
from PyQt6.QtGui import QFontDatabase  # noqa: E402
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QDialog, QDialogButtonBox, QLabel,  # noqa: E402
                             QListWidget, QListWidgetItem, QRadioButton, QVBoxLayout)

from .capture import ChangeDetector, edge_color, small_gray, text_color_for  # noqa: E402
from .config import DICTIONARY_PATH, FONT_PATH, Config  # noqa: E402
from .ocr import OcrUnavailableError, create_engine  # noqa: E402
from .ocr.winocr import OCR_CAPABILITY_CMD, japanese_ocr_available  # noqa: E402
from .overlay import OverlayItem, OverlayWindow, Toast  # noqa: E402
from .translate import Dictionary, TranslationService, contains_japanese  # noqa: E402

MODES = ("fixed", "free")
MODE_NAMES = {"fixed": "Sabit kutu", "free": "Serbest konum"}
VERTICAL_MIN_W = 160  # dikey yazı bloklarında çeviri kutusunun en küçük genişliği (px)
HOTKEY_IDS = {"toggle": 1, "retranslate": 2, "edit": 3, "mode": 4, "debug": 5, "quit": 6}

MSG_MODEL = "Çeviri modeli bulunamadı. Önce 'py -3.11 setup.py' çalıştırın."
MSG_OCR = ("Windows OCR Japonca dil paketi yok. Yönetici PowerShell'de çalıştırın:\n"
           + OCR_CAPABILITY_CMD)
MSG_PADDLE = "PaddleOCR kurulu değil ('setup.py --paddle'). Windows OCR kullanılıyor."
MSG_WINDOW_CLOSED = "Oyun penceresi kapandı. Aynı başlıkla yeniden açılırsa bağlanılacak."
MSG_FONT = "Font bulunamadı (assets/NotoSans.ttf). 'setup.py' çalıştırın."


class Pipeline(QThread):
    """Çeviri ve OCR bu thread'de çalışır; sonuçlar sinyalle arayüz thread'ine gelir."""

    fixed_result = pyqtSignal(str, dict)
    free_result = pyqtSignal(list, dict)
    error = pyqtSignal(str)
    ready = pyqtSignal()

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.q: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._mode = "fixed"
        self._capture: tuple[int, int, int, int] | None = None  # ekran koordinatı
        self._offset = (0, 0)  # yakalama alanının overlay içindeki sol üstü
        self._active = True
        self.service: TranslationService | None = None
        self._dict_mtime: float | None = None
        self._ocr = None
        self._ocr_failed = False

    # --- arayüz thread'inden çağrılır ---
    def set_capture(self, rect, offset) -> None:
        with self._lock:
            self._capture, self._offset = rect, offset

    def set_mode(self, mode: str) -> None:
        self.q.put(("mode", mode))

    def set_active(self, active: bool) -> None:
        self.q.put(("active", active))

    def submit_text(self, text: str) -> None:
        self.q.put(("text", text))

    def force(self) -> None:
        self.q.put(("force", None))

    def stop(self) -> None:
        self.q.put(("stop", None))
        self.wait(5000)

    # --- worker ---
    def _load_backend(self) -> bool:
        from .translate.nllb import ModelNotFoundError, NllbBackend
        try:
            backend = NllbBackend(self.cfg.model_path(), threads=self.cfg["threads"],
                                  beam_size=self.cfg["beam_size"], pivot=self.cfg["pivot"])
        except ModelNotFoundError:
            self.error.emit(MSG_MODEL)
            return False
        self.service = TranslationService(backend)
        self._reload_dictionary()
        return True

    def _reload_dictionary(self) -> None:
        try:
            mtime = DICTIONARY_PATH.stat().st_mtime if DICTIONARY_PATH.exists() else None
        except OSError:
            return
        if mtime == self._dict_mtime:
            return
        self._dict_mtime = mtime
        try:
            self.service.set_dictionary(Dictionary.load(DICTIONARY_PATH))
        except (OSError, ValueError):
            self.error.emit("dictionary.json okunamadı (geçersiz JSON).")

    def _translate(self, text: str) -> str:
        self._reload_dictionary()
        return self.service.translate(text)

    def _engine(self):
        if self._ocr is None and not self._ocr_failed:
            name = self.cfg["ocr_engine"]
            try:
                self._ocr = create_engine(name)
            except OcrUnavailableError:
                if name == "paddle":
                    self.error.emit(MSG_PADDLE)
                    try:
                        self._ocr = create_engine("windows")
                    except OcrUnavailableError:
                        self._ocr_failed = True
                        self.error.emit(MSG_OCR)
                else:
                    self._ocr_failed = True
                    self.error.emit(MSG_OCR)
        return self._ocr

    def run(self) -> None:
        if not self._load_backend():
            return
        self.ready.emit()
        from .capture import Grabber
        grabber = Grabber()
        detector = ChangeDetector(self.cfg["diff_pixel_threshold"], self.cfg["diff_min_pixels"],
                                  self.cfg["stable_ms"])
        period = 1.0 / max(1, self.cfg["capture_fps"])
        next_tick = time.monotonic()
        force = False
        while True:
            free = self._mode == "free" and self._active
            timeout = max(0.0, next_tick - time.monotonic()) if free else 0.5
            try:
                cmd, arg = self.q.get(timeout=timeout)
            except queue.Empty:
                cmd, arg = None, None
            if cmd == "stop":
                break
            if cmd == "mode":
                self._mode = arg
                detector.reset()
                if arg == "free":
                    self._engine()  # OCR motoru ilk karede değil, şimdi yüklensin
            elif cmd == "active":
                self._active = arg
                detector.reset()
            elif cmd == "force":
                force = True
            elif cmd == "text":
                self._handle_text(arg)
            if self._mode == "free" and self._active and (time.monotonic() >= next_tick or force):
                next_tick = time.monotonic() + period
                try:
                    self._tick(grabber, detector, force)
                except Exception as e:  # metin içeriği mesaja girmez
                    self.error.emit(f"Serbest konum hatası: {type(e).__name__}")
                force = False
        grabber.close()

    def _handle_text(self, text: str) -> None:
        t0 = time.perf_counter()
        try:
            out = self._translate(text)
        except Exception as e:
            self.error.emit(f"Çeviri hatası: {type(e).__name__}")
            return
        t = (time.perf_counter() - t0) * 1000
        self.fixed_result.emit(out, {"translate": t, "total": t})

    def _tick(self, grabber, detector: ChangeDetector, force: bool) -> None:
        with self._lock:
            rect, (ox, oy) = self._capture, self._offset
        if rect is None or rect[2] <= 0 or rect[3] <= 0:
            return
        t0 = time.perf_counter()
        img = grabber.grab(*rect)
        t_cap = time.perf_counter()
        fire = detector.feed(small_gray(img), t_cap * 1000)
        if not (fire or force):
            return
        engine = self._engine()
        if engine is None:
            return
        blocks = engine.recognize(img)
        t_ocr = time.perf_counter()
        items = []
        for b in blocks:
            bg = edge_color(img, b.x, b.y, b.w, b.h)
            x, w = b.x + ox, b.w
            if b.vertical and w < VERTICAL_MIN_W:
                # Türkçe yatay yazılır: dar sütunun etrafında okunabilir genişlikte kutu.
                x, w = max(0, x + w // 2 - VERTICAL_MIN_W // 2), VERTICAL_MIN_W
            items.append(OverlayItem(x, b.y + oy, w, b.h, self._translate(b.text), bg, text_color_for(bg)))
        t_tr = time.perf_counter()
        self.free_result.emit(items, {
            "capture": (t_cap - t0) * 1000, "ocr": (t_ocr - t_cap) * 1000,
            "translate": (t_tr - t_ocr) * 1000, "total": (t_tr - t0) * 1000,
        })


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == winapi.WM_HOTKEY:
                self.callback(int(msg.wParam))
                return True, 0
        return False, 0


class SelectDialog(QDialog):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("Oyun penceresini seç")
        self.resize(560, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Açık pencereler:"))
        self.list = QListWidget()
        for hwnd, title in winapi.list_windows(exclude_pid=os.getpid()):
            item = QListWidgetItem(title)
            item.setData(256, hwnd)
            self.list.addItem(item)
        lay.addWidget(self.list)
        lay.addWidget(QLabel("Mod:"))
        self.group = QButtonGroup(self)
        self.radios = {}
        for m in MODES:
            rb = QRadioButton(MODE_NAMES[m])
            self.group.addButton(rb)
            self.radios[m] = rb
            lay.addWidget(rb)
        self.radios["fixed"].setChecked(True)
        self.list.currentItemChanged.connect(self._on_select)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Başlat")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("İptal")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _on_select(self, item):
        if item is not None:
            self.radios[self.cfg.profile(item.text())["mode"]].setChecked(True)

    def result_value(self) -> tuple[int, str, str] | None:
        item = self.list.currentItem()
        if item is None:
            return None
        mode = next(m for m, rb in self.radios.items() if rb.isChecked())
        return item.data(256), item.text(), mode


class App(QObject):
    def __init__(self, qapp: QApplication, cfg: Config, hwnd: int, title: str, mode: str,
                 font_family: str, report: bool):
        super().__init__()
        self.qapp, self.cfg = qapp, cfg
        self.hwnd, self.title = hwnd, title
        self.report = report
        self.profile = cfg.profile(title)
        self.profile["mode"] = mode
        self.visible = True
        self.debug = False
        self.timings: dict = {}
        self.window_lost = False
        self._last_rects = None

        self.toast = Toast(font_family)
        self.overlay = OverlayWindow(font_family, cfg["font_max_px"], cfg["font_min_px"])
        self.overlay.box_changed.connect(self._on_box_changed)
        self.overlay.region_changed.connect(self._on_region_changed)
        self.overlay.painted.connect(self._on_painted)

        self.pipeline = Pipeline(cfg)
        self.pipeline.fixed_result.connect(self._on_fixed_result)
        self.pipeline.free_result.connect(self._on_free_result)
        self.pipeline.error.connect(self.notify)
        self.pipeline.ready.connect(lambda: self._emit_report({"event": "ready"}))

        self._sync_geometry()
        self.overlay.set_mode(mode, self.profile["box"], self.profile["region"])
        self.overlay.show()
        self._update_capture()
        self.pipeline.set_mode(mode)
        self.pipeline.start()

        self.hotkeys = HotkeyFilter(self._on_hotkey)
        qapp.installNativeEventFilter(self.hotkeys)
        for name, hk_id in HOTKEY_IDS.items():
            spec = cfg["hotkeys"].get(name)
            try:
                ok = bool(spec) and winapi.register_hotkey(self.overlay.hwnd(), hk_id, spec)
            except ValueError:
                ok = False
            if not ok:
                self.notify(f"Kısayol kaydedilemedi: {spec} ({name})")

        qapp.clipboard().dataChanged.connect(self._on_clipboard)
        self.timer = QTimer(self, interval=200, timeout=self._sync_geometry)
        self.timer.start()

        if self.cfg["ocr_engine"] != "paddle" and not japanese_ocr_available():
            self.notify(MSG_OCR, 15)
        self._emit_report({"event": "started", "overlay_hwnd": self.overlay.hwnd(),
                           "exstyle": winapi.get_exstyle(self.overlay.hwnd()),
                           "affinity": winapi.display_affinity(self.overlay.hwnd())})

    # --- yardımcılar ---
    def notify(self, text: str, seconds: float = 6.0) -> None:
        self.toast.show_message(text, seconds)
        self._emit_report({"event": "notify"})

    def _emit_report(self, data: dict) -> None:
        if self.report:  # yalnızca test için; metin içeriği basılmaz
            print(json.dumps(data), flush=True)

    def _sync_geometry(self) -> None:
        if not winapi.is_window(self.hwnd):
            if not self.window_lost:
                self.window_lost = True
                self.overlay.hide()
                self.pipeline.set_active(False)
                self.notify(MSG_WINDOW_CLOSED)
                self._emit_report({"event": "window_closed"})
            hwnd = winapi.find_window(self.title)
            if hwnd is None:
                return
            self.hwnd = hwnd
        if self.window_lost:
            self.window_lost = False
            if self.visible:
                self.overlay.show()
            self.pipeline.set_active(self.visible)
        if winapi.is_minimized(self.hwnd):
            return
        rect = winapi.client_rect_screen(self.hwnd)
        if rect is None:
            return
        if tuple(self.overlay.geometry().getRect()) != rect:
            self.overlay.set_target_rect(*rect)
            self._update_capture()

    def _update_capture(self) -> None:
        g = self.overlay.geometry()
        region = self.profile["region"]
        if region:
            x, y, w, h = region
            x, y = max(0, x), max(0, y)
            w, h = min(w, g.width() - x), min(h, g.height() - y)
            self.pipeline.set_capture((g.x() + x, g.y() + y, w, h), (x, y))
        else:
            self.pipeline.set_capture((g.x(), g.y(), g.width(), g.height()), (0, 0))

    def _show_debug(self) -> None:
        if not self.debug:
            self.overlay.set_debug(None)
            return
        t = self.timings
        names = [("capture", "yakalama"), ("ocr", "OCR"), ("translate", "çeviri"), ("draw", "çizim"),
                 ("total", "toplam")]
        lines = [f"Mod: {MODE_NAMES[self.profile['mode']]}"]
        lines += [f"{label:9s}: {t[k]:7.1f} ms" for k, label in names if k in t]
        self.overlay.set_debug("\n".join(lines))

    # --- sinyaller ---
    def _on_clipboard(self) -> None:
        if self.profile["mode"] != "fixed" or not self.visible:
            return
        text = self.qapp.clipboard().text()
        if text and contains_japanese(text):
            self.pipeline.submit_text(text.replace("\r", "").replace("\n", ""))

    def _on_fixed_result(self, text: str, timings: dict) -> None:
        if self.profile["mode"] != "fixed":
            return
        self.timings = dict(timings)
        self.overlay.set_fixed_text(text)

    def _on_free_result(self, items: list, timings: dict) -> None:
        if self.profile["mode"] != "free":
            return
        self.timings = dict(timings)
        self.overlay.set_items(items)

    def _on_painted(self, rects: list, draw_ms: float) -> None:
        if self.timings and "draw" not in self.timings:
            self.timings["draw"] = draw_ms
            self.timings["total"] = self.timings.get("total", 0) + draw_ms
            self._emit_report({"event": "timings", **{k: round(v, 1) for k, v in self.timings.items()}})
            self._show_debug()
        if rects != self._last_rects:
            self._last_rects = rects
            g = self.overlay.geometry()
            self._emit_report({"event": "overlay", "mode": self.profile["mode"],
                               "rects": [[x + g.x(), y + g.y(), w, h] for x, y, w, h in rects]})

    def _on_box_changed(self, box: list) -> None:
        self.profile["box"] = box

    def _on_region_changed(self, region) -> None:
        self.profile["region"] = region
        self._update_capture()

    def _on_hotkey(self, hk_id: int) -> None:
        name = next((n for n, i in HOTKEY_IDS.items() if i == hk_id), None)
        if name == "toggle":
            self.visible = not self.visible
            self.overlay.setVisible(self.visible)
            self.pipeline.set_active(self.visible)
        elif name == "retranslate":
            if self.profile["mode"] == "free":
                self.pipeline.force()
            else:
                self._on_clipboard()
        elif name == "edit":
            editing = not self.overlay.edit
            self.overlay.set_edit(editing)
            if not editing:
                self.cfg.save_profile(self.title, self.profile)
                self._update_capture()
                self.pipeline.force()
            self._emit_report({"event": "edit", "on": editing,
                               "exstyle": winapi.get_exstyle(self.overlay.hwnd())})
        elif name == "mode":
            mode = "free" if self.profile["mode"] == "fixed" else "fixed"
            self.profile["mode"] = mode
            self.overlay.set_mode(mode, self.profile["box"], self.profile["region"])
            self.pipeline.set_mode(mode)
            self.cfg.save_profile(self.title, self.profile)
            self.notify(f"Mod: {MODE_NAMES[mode]}", 2)
        elif name == "debug":
            self.debug = not self.debug
            self._show_debug()
        elif name == "quit":
            self.quit()

    def quit(self) -> None:
        for hk_id in HOTKEY_IDS.values():
            winapi.unregister_hotkey(self.overlay.hwnd(), hk_id)
        self.pipeline.stop()
        self.qapp.quit()


def load_font() -> str | None:
    if FONT_PATH.exists():
        fid = QFontDatabase.addApplicationFont(str(FONT_PATH))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams:
            return fams[0]
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", help="Seçim penceresini atla, bu başlıktaki pencereye bağlan")
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--test-report", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    qapp = QApplication(sys.argv[:1])
    qapp.setQuitOnLastWindowClosed(False)
    cfg = Config()
    family = load_font()

    if args.window:
        hwnd = None
        for _ in range(50):
            hwnd = winapi.find_window(args.window)
            if hwnd:
                break
            time.sleep(0.1)
        if not hwnd:
            print("Pencere bulunamadı", file=sys.stderr)
            return 2
        title = args.window
        mode = args.mode or cfg.profile(title)["mode"]
    else:
        dlg = SelectDialog(cfg)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.result_value() is None:
            return 0
        hwnd, title, mode = dlg.result_value()
        if args.mode:
            mode = args.mode

    app = App(qapp, cfg, hwnd, title, mode, family or qapp.font().family(), args.test_report)
    if family is None:
        app.notify(MSG_FONT)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
