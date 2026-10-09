"""Ana uygulama: pencere/mod seçimi, kısayollar, pano, overlay ve worker thread'i bağlar.

Çalıştırma:  venv\\Scripts\\python.exe -m src.app [--window BAŞLIK] [--mode fixed|free] [--lang ja|ko|en]
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
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QDialog, QDialogButtonBox, QFileDialog,  # noqa: E402
                             QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QRadioButton,
                             QVBoxLayout)

from .capture import ChangeDetector, edge_color, small_gray, text_color_for  # noqa: E402
from .config import DICTIONARY_PATH, FONT_PATH, Config  # noqa: E402
from .ocr import OcrUnavailableError, create_engine  # noqa: E402
from .ocr.merge import merge_all  # noqa: E402
from .ocr.stabilize import TextStabilizer, completes  # noqa: E402
from .ocr.winocr import ocr_capability_cmd, ocr_language_available  # noqa: E402
from .overlay import OverlayItem, OverlayWindow, Toast  # noqa: E402
from .translate import LANGS, Dictionary, TranslationService, contains_language  # noqa: E402
from .translate.text import looks_complete  # noqa: E402

MODES = ("fixed", "free")
MODE_NAMES = {"fixed": "Sabit kutu", "free": "Serbest konum"}
VERTICAL_MIN_W = 160  # dikey yazı bloklarında çeviri kutusunun en küçük genişliği (px)
HOTKEY_IDS = {"toggle": 1, "retranslate": 2, "edit": 3, "mode": 4, "debug": 5, "quit": 6, "settings": 7}

from .translate.factory import MSG_MODEL, MSG_SUGOI  # noqa: E402,F401
def msg_ocr(lang: str) -> str:
    return (f"Windows OCR {LANGS[lang].name} dil paketi yok. Yönetici PowerShell'de çalıştırın:\n"
            + ocr_capability_cmd(lang))


MSG_OCR = msg_ocr("ja")
MSG_PADDLE = "PaddleOCR kurulu değil ('setup.py --paddle'). Windows OCR kullanılıyor."
MSG_WINDOW_CLOSED = "Oyun penceresi kapandı. Aynı başlıkla yeniden açılırsa bağlanılacak."
MSG_FONT = "Font bulunamadı (assets/NotoSans.ttf). 'setup.py' çalıştırın."
MSG_READY = {
    "fixed": "Hazır - Sabit kutu modu.\nPanoya {lang} metin bekleniyor (Textractor gerekir).\n"
             "Ekrandaki yazıyı okumak için Ctrl+Alt+M ile Serbest konum moduna geçin.",
    "free": "Hazır - Serbest konum modu.\nOyun ekranındaki {lang} yazılar okunuyor.\nAyarlar: Ctrl+Alt+S",
}
MSG_BLACK = ("Oyun ekranı siyah yakalanıyor; yazı okunamaz.\n"
             "Oyunun görüntü ayarlarında pencereli / çerçevesiz modu ve varsa\n"
             "farklı bir grafik modunu (DirectX/OpenGL) deneyin.")


def console(msg: str) -> None:
    """Başlatan terminale durum satırı (metin içeriği yazılmaz)."""
    try:
        print(f"[çeviri] {msg}", flush=True)
    except (OSError, ValueError):
        pass  # konsolsuz çalıştırma


class Pipeline(QThread):
    """Çeviri ve OCR bu thread'de çalışır; sonuçlar sinyalle arayüz thread'ine gelir."""

    fixed_result = pyqtSignal(str, dict)
    free_result = pyqtSignal(list, dict)
    error = pyqtSignal(str)
    ready = pyqtSignal()
    status = pyqtSignal(str)
    ocr_debug = pyqtSignal(list)  # yalnızca test raporu: blok koordinatları, metin yok

    def __init__(self, cfg: Config, lang: str = "ja"):
        super().__init__()
        self.cfg = cfg
        self.lang = lang  # kaynak dil; hedef her zaman Türkçe
        self.q: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._mode = "fixed"
        self._capture: tuple[int, int, int, int] | None = None  # ekran koordinatı
        self._offset = (0, 0)  # yakalama alanının overlay içindeki sol üstü
        self._has_region = False  # kullanıcı tarama alanını sınırladı mı (Ctrl+Alt+E)
        self._active = True
        self.service: TranslationService | None = None
        self._dict_mtime: float | None = None
        self._ocr = None
        self._ocr_failed = False
        self._black = False
        self.gen = 0  # her tıklamada artar; tıklamadan önce başlamış OCR sonucu atılır
        # Gecikme dökümü (yalnızca süreler, metin yok): yeni bir çeviri ekrana gelince terminale yazılır.
        self._advance_at: float | None = None
        self._first_seen: float | None = None
        self._reads = 0
        self._ocr_acc = 0.0
        self._tr_acc = 0.0
        self._shown_texts: set[str] = set()
        # Yazı harf harf akarken yarım metni çevirmemek için: aynı metin iki kez okunmalı.
        self.stabilizer = TextStabilizer(looks_complete=lambda text: looks_complete(text, self.lang))
        self._recheck_at: float | None = None
        # Yazı akarken tıklandı: oyun yazının tamamını getirir. (zaman, tıklamadan önceki yarım metinler)
        self._complete_check: tuple[float, list[str]] | None = None

    # --- arayüz thread'inden çağrılır ---
    def set_capture(self, rect, offset, has_region: bool = False) -> None:
        with self._lock:
            self._capture, self._offset, self._has_region = rect, offset, has_region

    def set_mode(self, mode: str) -> None:
        self.q.put(("mode", mode))

    def set_active(self, active: bool) -> None:
        self.q.put(("active", active))

    def submit_text(self, text: str) -> None:
        self.q.put(("text", text))

    def advance(self) -> None:
        """Oyunda tıklandı (sahne ilerliyor): yeni ekran durulunca OCR yeniden çalışsın."""
        self.gen += 1
        self._advance_at = time.monotonic()
        self.q.put(("advance", None))

    def force(self) -> None:
        self.q.put(("force", None))

    def stop(self) -> None:
        self.q.put(("stop", None))
        self.wait(5000)

    # --- worker ---
    def _load_backend(self) -> bool:
        from .translate.factory import NoModelError, build_service
        try:
            self.service = build_service(self.cfg, self.lang, warn=self.error.emit)
        except NoModelError as e:
            self.error.emit(str(e))
            return False
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
        t = time.perf_counter()
        out = self.service.translate(text)
        self._tr_acc += (time.perf_counter() - t) * 1000
        return out

    def _engine(self):
        if self._ocr is None and not self._ocr_failed:
            name = self.cfg["ocr_engine"]
            try:
                self._ocr = create_engine(name, self.lang)
            except OcrUnavailableError:
                if name == "paddle":
                    self.error.emit(MSG_PADDLE)
                    try:
                        self._ocr = create_engine("windows", self.lang)
                    except OcrUnavailableError:
                        self._ocr_failed = True
                        self.error.emit(msg_ocr(self.lang))
                else:
                    self._ocr_failed = True
                    self.error.emit(msg_ocr(self.lang))
        return self._ocr

    def run(self) -> None:
        if not self._load_backend():
            return
        self.ready.emit()
        from .capture import Grabber
        grabber = Grabber()
        detector = ChangeDetector(self.cfg["diff_pixel_threshold"], self.cfg["diff_min_pixels"],
                                  self.cfg["stable_ms"], self.cfg["max_wait_ms"])
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
            elif cmd == "advance":
                # Yazı hâlâ akıyorken tıklandıysa bu "tamamla" tıkıdır: kısa süre sonra bir kez oku,
                # metin akan yazının devamıysa doğrulama beklemeden çevir. Değilse ("sonraki sayfa")
                # her şey normal yoldan doğrulanır.
                # "Yazı akıyor" = onay bekleyen metin var ya da sayfa değiştiğinden beri henüz hiçbir
                # çeviri gösterilmedi (1. tık sayfa, 2. tık tamamla düzeni).
                typing = self.stabilizer.candidates()
                in_progress = bool(typing) or not self.stabilizer.has_shown()
                detector.reset()
                self.stabilizer.reset()
                self._recheck_at = None
                self._first_seen, self._shown_texts = None, set()  # süre ölçümü yeni sayfadan başlasın
                self._complete_check = ((time.monotonic() + self.cfg["complete_click_ms"] / 1000, typing)
                                        if in_progress else None)
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
            rect, (ox, oy), has_region = self._capture, self._offset, self._has_region
        if rect is None or rect[2] <= 0 or rect[3] <= 0:
            return
        gen = self.gen
        t0 = time.perf_counter()
        img = grabber.grab(*rect)
        t_cap = time.perf_counter()
        black = float(img[::4, ::4, :3].max()) < 16
        if black != self._black:
            self._black = black
            if black:
                self.error.emit(MSG_BLACK)
        fire = detector.feed(small_gray(img), t_cap * 1000)
        recheck_due = self._recheck_at is not None and time.monotonic() >= self._recheck_at
        completion = self._complete_check
        if completion is not None and time.monotonic() < completion[0]:
            completion = None
        if not (fire or force or recheck_due or completion):
            return
        engine = self._engine()
        if engine is None:
            return
        blocks = engine.recognize(img)
        if has_region and self.cfg["region_single_block"]:
            blocks = merge_all(blocks, self.lang)  # diyalog kutusundaki yazı tek replik
        t_ocr = time.perf_counter()
        if blocks and self._first_seen is None and {b.text for b in blocks} - self._shown_texts:
            self._first_seen, self._reads, self._ocr_acc, self._tr_acc = time.monotonic(), 0, 0.0, 0.0
        self._reads += 1
        self._ocr_acc += (t_ocr - t_cap) * 1000
        done = []
        if completion is not None:
            self._complete_check = None
            # Tamamlandı say: akan yarım metnin devamı ya da cümle sonu işaretiyle bitiyor. Sayfa
            # değiştiren bir tık olduysa yeni sayfa henüz akmaya başlamıştır; ikisi de tutmaz ve
            # metin normal yoldan doğrulanır.
            done = [b for b in blocks
                    if looks_complete(b.text, self.lang) or any(completes(p, b.text) for p in completion[1])]
        if done:  # tıklamayla tamamlanan yazı: doğrulama yok, hemen çevir
            ready, recheck = self.stabilizer.show_now(done), False
        else:
            ready, recheck = self.stabilizer.feed(blocks)
        self.ocr_debug.emit([round(t0, 3), "tamamla" if completion else "",
                             [[b.x + ox, b.y + oy, b.w, b.h, b in ready, len(b.text)] for b in blocks]])
        self._recheck_at = time.monotonic() + self.cfg["confirm_ms"] / 1000 if recheck else None
        # Önden çeviri: cümle sonu işaretiyle biten aday metin büyük ihtimalle tamamlanmıştır.
        # Doğrulama okumasını beklerken şimdi çevir (önbelleğe girer); doğrulanınca anında gösterilir.
        # Ekrana yine yalnızca doğrulanmış metin çıkar.
        # Yalnızca en olası tek aday (en uzun, cümle sonuyla biten): işlemci meşgulken boşa iş yapma.
        likely = [t for t in self.stabilizer.candidates() if looks_complete(t, self.lang) and len(t) >= 4]
        if likely:
            self._translate(max(likely, key=len))
        self.status.emit(f"OCR: {len(blocks)} {LANGS[self.lang].name} blok okundu, {len(ready)} çeviri gösteriliyor"
                         + (" (yazı henüz akıyor / doğrulanıyor)" if recheck else "")
                         + f" ({(t_ocr - t_cap) * 1000:.0f} ms)")
        items = []
        for b in ready:  # yalnızca tamamlanmış (iki okumada benzer, uzamayan) metin çevrilir
            bg = edge_color(img, b.x, b.y, b.w, b.h)
            x, w = b.x + ox, b.w
            if b.vertical and w < VERTICAL_MIN_W:
                # Türkçe yatay yazılır: dar sütunun etrafında okunabilir genişlikte kutu.
                x, w = max(0, x + w // 2 - VERTICAL_MIN_W // 2), VERTICAL_MIN_W
            items.append(OverlayItem(x, b.y + oy, w, b.h, self._translate(b.text), bg, text_color_for(bg)))
        t_tr = time.perf_counter()
        self._report_latency(ready)
        self.free_result.emit(items, {
            "capture": (t_cap - t0) * 1000, "ocr": (t_ocr - t_cap) * 1000,
            "translate": (t_tr - t_ocr) * 1000, "total": (t_tr - t0) * 1000, "gen": gen,
        })


    def _report_latency(self, ready) -> None:
        texts = {b.text for b in ready}
        new = texts - self._shown_texts
        self._shown_texts = texts
        if not new or self._first_seen is None:
            return
        now = time.monotonic()
        total = (now - self._first_seen) * 1000
        wait = max(0.0, total - self._ocr_acc - self._tr_acc)
        msg = (f"[süre] Çeviri ekranda: yazı ilk okunduktan {total:.0f} ms sonra | {self._reads} OCR okuması "
               f"(toplam {self._ocr_acc:.0f} ms) | çeviri {self._tr_acc:.0f} ms | bekleme {wait:.0f} ms")
        if self._advance_at is not None and now - self._advance_at < 15:
            msg += f" | tıklamadan beri {(now - self._advance_at) * 1000:.0f} ms"
        self.status.emit(msg)
        self._first_seen = None


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
        self.radios["free"].setChecked(True)
        lay.addWidget(QLabel("Oyunun dili (çeviri her zaman Türkçeye):"))
        self.lang_group = QButtonGroup(self)
        self.lang_radios = {}
        for code, lang in LANGS.items():
            rb = QRadioButton(lang.name)
            self.lang_group.addButton(rb)
            self.lang_radios[code] = rb
            lay.addWidget(rb)
        self.lang_radios["ja"].setChecked(True)
        self.list.currentItemChanged.connect(self._on_select)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        self.image_paths: list | None = None
        lay.addWidget(QLabel("Ya da bilgisayardaki resimleri çevir (yukarıdaki dil seçimi geçerli):"))
        row = QHBoxLayout()
        for label, pick in (("Klasör aç...", self._pick_folder), ("Resim aç...", self._pick_files)):
            btn = QPushButton(label)
            btn.clicked.connect(pick)
            row.addWidget(btn)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Başlat")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("İptal")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _on_select(self, item):
        if item is not None:
            prof = self.cfg.profile(item.text())
            self.radios[prof["mode"]].setChecked(True)
            self.lang_radios[prof["lang"]].setChecked(True)

    # Windows'un normal dosya penceresi (Masaüstü, İndirilenler kısayollarıyla), Masaüstünde açılır.
    @staticmethod
    def _start_dir() -> str:
        from PyQt6.QtCore import QStandardPaths
        return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Resim klasörünü seç", self._start_dir())
        if d:
            self.image_paths = [d]
            self.accept()

    def _pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Resim seç", self._start_dir(), "Resimler (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)")
        if files:
            self.image_paths = files
            self.accept()

    def selected_lang(self) -> str:
        return next(c for c, rb in self.lang_radios.items() if rb.isChecked())

    def result_value(self) -> tuple[int, str, str, str] | None:
        item = self.list.currentItem()
        if item is None:
            return None
        mode = next(m for m, rb in self.radios.items() if rb.isChecked())
        lang = next(c for c, rb in self.lang_radios.items() if rb.isChecked())
        return item.data(256), item.text(), mode, lang


class App(QObject):
    def __init__(self, qapp: QApplication, cfg: Config, hwnd: int, title: str, mode: str,
                 font_family: str, report: bool, lang: str = "ja"):
        super().__init__()
        self.qapp, self.cfg = qapp, cfg
        self.hwnd, self.title = hwnd, title
        self.report = report
        self.profile = cfg.profile(title)
        self.profile["mode"] = mode
        self.profile["lang"] = lang
        cfg.save_profile(title, self.profile)  # seçilen mod ve dil bu oyun için hatırlansın
        self.visible = True
        self.debug = False
        self.timings: dict = {}
        self.window_lost = False
        self._last_rects = None

        self.toast = Toast(font_family)
        self.overlay = OverlayWindow(font_family, cfg["font_max_px"], cfg["font_min_px"])
        self.bundled_family = font_family
        self.settings_dialog = None
        self._apply_style(cfg.data)
        self.overlay.box_changed.connect(self._on_box_changed)
        self.overlay.region_changed.connect(self._on_region_changed)
        self.overlay.painted.connect(self._on_painted)

        self.pipeline = Pipeline(cfg, lang)
        self.pipeline.fixed_result.connect(self._on_fixed_result)
        self.pipeline.free_result.connect(self._on_free_result)
        self.pipeline.error.connect(self.notify)
        self.pipeline.ready.connect(self._on_ready)
        if not report:
            self.pipeline.status.connect(console)
        else:
            self.pipeline.status.connect(lambda _: self._emit_report({"event": "ocr"}))
            self.pipeline.ocr_debug.connect(lambda d: self._emit_report(
                {"event": "ocr_blocks", "grab_t": d[0], "kind": d[1], "blocks": d[2]}))

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
        # Oyunda tıklama / Enter / Boşluk = sahne ilerliyor: eski çeviri hemen kalksın,
        # yoksa aynı yerde çıkan yeni yazıyı örter.
        self._pressed: set[int] = set()
        for vk in (winapi.VK_LBUTTON, winapi.VK_RETURN, winapi.VK_SPACE):
            winapi.key_down(vk)  # açılıştan önceki tıklamaların "basıldı" bitini temizle
        # Ayar canlı açılıp kapatılabildiği için yoklama hep çalışır; kapalıysa hiçbir şey yapmaz.
        self.input_timer = QTimer(self, interval=25, timeout=self._poll_advance)
        self.input_timer.start()

        if self.cfg["ocr_engine"] != "paddle" and not ocr_language_available(lang):
            self.notify(msg_ocr(lang), 15)
        self._emit_report({"event": "started", "overlay_hwnd": self.overlay.hwnd(),
                           "exstyle": winapi.get_exstyle(self.overlay.hwnd()),
                           "affinity": winapi.display_affinity(self.overlay.hwnd())})

    # --- yardımcılar ---
    def notify(self, text: str, seconds: float = 6.0) -> None:
        self.toast.show_message(text, seconds)
        if not self.report:
            console(text.replace("\n", " "))
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
            self.pipeline.set_capture((g.x() + x, g.y() + y, w, h), (x, y), has_region=True)
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
        lang = self.profile["lang"]
        if text and contains_language(text, lang):
            if LANGS[lang].joins_without_space:  # Japonca: satır sonları boşluksuz birleşir
                self.pipeline.submit_text(text.replace("\r", "").replace("\n", ""))
            else:
                self.pipeline.submit_text(" ".join(text.split()))

    def _ready_msg(self, mode: str) -> str:
        return MSG_READY[mode].format(lang=LANGS[self.profile["lang"]].name)

    def _on_ready(self) -> None:
        self._emit_report({"event": "ready"})
        if not self.report:
            self.notify(self._ready_msg(self.profile["mode"]), 8)

    def _on_fixed_result(self, text: str, timings: dict) -> None:
        if self.profile["mode"] != "fixed":
            return
        if not self.report:
            console(f"Panodan metin çevrildi ({timings['translate']:.0f} ms)")
        self.timings = dict(timings)
        self.overlay.set_fixed_text(text)

    def _poll_advance(self) -> None:
        if (not self.cfg["clear_on_click"] or self.profile["mode"] != "free" or not self.visible
                or self.overlay.edit):
            return
        now = {vk for vk in (winapi.VK_LBUTTON, winapi.VK_RETURN, winapi.VK_SPACE) if winapi.key_down(vk)}
        new = now - self._pressed
        self._pressed = now
        # Hızlı tıklama: basılıp bırakılmış (yalnızca "basıldı" biti) -> bir sonraki yoklamada yeniden
        # basılabilsin diye basılı sayma.
        self._pressed = {vk for vk in now if winapi.user32.GetAsyncKeyState(vk) & 0x8000}
        if not new:
            return
        if winapi.VK_LBUTTON in new:
            # Fare: imlecin altındaki pencere oyun mu? (Ön plan kontrolü işe yaramaz: tıklama
            # anında oyun henüz öne gelmemiş olabilir.)
            x, y = winapi.cursor_pos()
            if not (self.overlay.geometry().contains(x, y) and winapi.root_window_at(x, y) == self.hwnd):
                return
        elif not winapi.is_foreground(self.hwnd):  # Enter / Boşluk yalnızca oyun öndeyken
            return
        self.pipeline.advance()
        if self.overlay.items:
            self.overlay.set_items([])
        self._emit_report({"event": "advance", "t": round(time.perf_counter(), 3)})

    def _on_free_result(self, items: list, timings: dict) -> None:
        if self.profile["mode"] != "free" or timings.pop("gen", None) != self.pipeline.gen:
            return  # tıklamadan önceki ekrana ait sonuç
        if items == self.overlay.items:
            return  # içerik aynı: yeniden çizme
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
            self.notify(self._ready_msg(mode), 5)
        elif name == "debug":
            self.debug = not self.debug
            self._show_debug()
        elif name == "quit":
            self.quit()
        elif name == "settings":
            self.open_settings()

    # --- ayarlar penceresi ---
    def _apply_style(self, v: dict) -> None:
        self.overlay.set_style(v["font_family"] or self.bundled_family, v["font_max_px"], v["font_min_px"],
                               v["font_bold"], v["text_color"], v["box_opacity"], v["follow_original"])

    def open_settings(self) -> None:
        from .overlay.settings_dialog import STYLE_KEYS, SettingsDialog
        if self.settings_dialog is not None and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        dlg = SettingsDialog({k: self.cfg[k] for k in STYLE_KEYS}, self.bundled_family,
                             on_change=self._apply_style)

        def save():
            ja_before = self.cfg["ja_model"]
            self.cfg.data.update(dlg.values())
            self.cfg.save()
            self._apply_style(self.cfg.data)
            if self.cfg["ja_model"] != ja_before:
                self.notify("Japonca çeviri yöntemi uygulama yeniden açılınca değişecek.", 5)

        dlg.accepted.connect(save)
        self.settings_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

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


def run_image_mode(qapp: QApplication, cfg: Config, paths: list, lang: str, family: str | None) -> int:
    from pathlib import Path

    from .imagemode import ImageViewer, list_images
    files, start = list_images([Path(p) for p in paths])
    family = family or qapp.font().family()
    toast = Toast(family)

    def notify(msg: str, seconds: float = 6.0):
        toast.show_message(msg, seconds)
        console(msg.replace("\n", " "))

    console(f"Resim modu: {len(files)} resim | Dil: {LANGS[lang].name} -> Türkçe | Çeviri modeli yükleniyor...")
    viewer = ImageViewer(cfg, lang, files, start, family, notify)
    viewer.show()
    qapp.setQuitOnLastWindowClosed(True)
    if not files:
        notify("Seçilen yerde resim bulunamadı. Resimleri pencereye sürükleyip bırakabilirsiniz.")
    if not ocr_language_available(lang):
        notify(msg_ocr(lang), 15)
    return qapp.exec()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", help="Seçim penceresini atla, bu başlıktaki pencereye bağlan")
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--lang", choices=sorted(LANGS), help="oyunun dili (ja, ko, en)")
    ap.add_argument("--test-report", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("images", nargs="*", help="resim modu: resim dosyaları ya da klasör")
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
        lang = args.lang or cfg.profile(title)["lang"]
    elif args.images:
        return run_image_mode(qapp, cfg, args.images, args.lang or "ja", family)
    else:
        dlg = SelectDialog(cfg)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return 0
        if dlg.image_paths:
            return run_image_mode(qapp, cfg, dlg.image_paths, args.lang or dlg.selected_lang(), family)
        if dlg.result_value() is None:
            return 0
        hwnd, title, mode, lang = dlg.result_value()
        if args.mode:
            mode = args.mode
        if args.lang:
            lang = args.lang

    if not args.test_report:
        console(f"Pencere: {title} | Mod: {MODE_NAMES[mode]} | Dil: {LANGS[lang].name} -> Türkçe | "
                "Çeviri modeli yükleniyor...")
    app = App(qapp, cfg, hwnd, title, mode, family or qapp.font().family(), args.test_report, lang)
    if family is None:
        app.notify(MSG_FONT)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
