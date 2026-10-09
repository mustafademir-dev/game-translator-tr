"""Uçtan uca testler: sahte oyun + gerçek uygulama (ağ erişimi kapalı başlatılır).

Gerçek masaüstü gerektirir (Windows, açık oturum). Model yoksa atlanır.
"""
from __future__ import annotations

import ctypes
import json
import queue
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import pytest

from src.config import Config
from src.ocr.winocr import japanese_ocr_available, ocr_language_available

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

pytestmark = pytest.mark.skipif(not (Config().model_path() / "model.bin").exists(),
                                reason="Çeviri modeli kurulu değil (setup.py)")


class Proc:
    def __init__(self, args: list[str]):
        self.p = subprocess.Popen([PY, *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, encoding="utf-8", errors="replace")
        self.events: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            line = line.strip()
            if line.startswith("{"):
                try:
                    self.events.put(json.loads(line))
                except ValueError:
                    pass

    def wait_for(self, pred, timeout: float):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                ev = self.events.get(timeout=0.2)
            except queue.Empty:
                if self.p.poll() is not None:
                    break
                continue
            if pred(ev):
                return ev
        return None

    def kill(self):
        if self.p.poll() is None:
            self.p.kill()
        self.p.wait(10)


def overlaps(a, b, min_frac=0.5) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy >= min_frac * bw * bh


def set_clipboard(text: str) -> None:
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    data = text.encode("utf-16-le") + b"\0\0"
    for _ in range(20):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.05)
    try:
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(0x0042, len(data))
        ctypes.memmove(k32.GlobalLock(h), data, len(data))
        k32.GlobalUnlock(h)
        u32.SetClipboardData(13, h)  # CF_UNICODETEXT
    finally:
        u32.CloseClipboard()


def click(x: int, y: int, hold: float = 0.08) -> None:
    u32 = ctypes.windll.user32
    # Test süreci de fiziksel piksel kullanmalı (ekran ölçekliyse imleç kayar).
    u32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    u32.SetCursorPos(x, y)
    time.sleep(0.1)
    u32.mouse_event(0x0002, 0, 0, 0, 0)  # sol tuş bas
    time.sleep(hold)  # gerçek bir tıklama gibi kısa süre basılı
    u32.mouse_event(0x0004, 0, 0, 0, 0)  # bırak


@pytest.fixture
def procs():
    started: list[Proc] = []
    yield started
    for p in started:
        p.kill()
    # Uygulama seçilen mod/dili profile yazar; testler kullanıcı ayarında iz bırakmasın.
    cfg = Config()
    for title in [t for t in cfg.data["profiles"] if t.startswith("Fake Game E2E")]:
        cfg.data["profiles"].pop(title)
    cfg.save()


def start_game(procs, title, *extra) -> Proc:
    g = Proc(["tools/fake_game.py", "--title", title, "--at", "60,60", "--topmost", *extra])
    procs.append(g)
    return g


def start_app(procs, title, mode, lang="ja") -> Proc:
    a = Proc(["tests/offline_launcher.py", "--window", title, "--mode", mode, "--lang", lang,
              "--test-report"])
    procs.append(a)
    return a


@pytest.mark.skipif(not japanese_ocr_available(), reason="Windows OCR Japonca dil paketi yok")
@pytest.mark.parametrize("extra", [[], ["--typewriter"]], ids=["normal", "typewriter"])
def test_free_mode_box_appears_over_known_line(procs, extra):
    title = "Fake Game E2E Free"
    game = start_game(procs, title, "--line", "0", "--pos", "250,320", "--sizes", "30",
                      "--interval", "1000", *extra)
    line = game.wait_for(lambda e: e["event"] == "line", 15)
    assert line, "sahte oyun replik göstermedi"
    app = start_app(procs, title, "free")
    started = app.wait_for(lambda e: e["event"] == "started", 30)
    assert started, "uygulama başlamadı"
    assert started["exstyle"] & 0x20 and started["exstyle"] & 0x80000, "click-through stili yok"
    assert started["affinity"] == 0x11, "overlay yakalamadan hariç değil"
    ev = app.wait_for(lambda e: e["event"] == "overlay" and e["mode"] == "free"
                      and any(overlaps(r, line["rect"]) for r in e["rects"]), 90)
    assert ev, "replik konumunda çeviri kutusu oluşmadı"
    # Overlay yakalamadan hariç: kendi kutusunu yeniden OCR'a sokmamalı, kutu sayısı sabit kalmalı.
    time.sleep(3)
    later = [e for e in iter_events(app) if e["event"] == "overlay"]
    assert all(len(e["rects"]) == len(ev["rects"]) for e in later)


def iter_events(proc: Proc):
    while True:
        try:
            yield proc.events.get_nowait()
        except queue.Empty:
            return


def test_fixed_mode_clipboard_and_click_through(procs):
    title = "Fake Game E2E Fixed"
    game = start_game(procs, title, "--blank")
    time.sleep(1.5)
    app = start_app(procs, title, "fixed")
    assert app.wait_for(lambda e: e["event"] == "ready", 60), "çeviri modeli yüklenmedi"
    set_clipboard("田中さん、今日は学校に来ないんですか？")
    ev = app.wait_for(lambda e: e["event"] == "overlay" and e["mode"] == "fixed" and e["rects"], 30)
    assert ev, "panodaki metin kutuda çıkmadı"
    x, y, w, h = ev["rects"][0]
    cx, cy = x + w // 2, y + h // 2
    click(cx, cy)
    got = game.wait_for(lambda e: e["event"] == "click", 5)
    assert got, "tıklama alttaki pencereye geçmedi"
    assert abs(got["x"] - cx) <= 2 and abs(got["y"] - cy) <= 2


def test_offline_selfcheck():
    out = subprocess.run([PY, "tests/offline_launcher.py", "--selfcheck"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=300).stdout
    assert "translate_ok" in out
    assert "ocr_ok" in out or "ocr_skipped" in out
    assert "paddle_ok" in out or "paddle_skipped" in out
    assert "network_attempts=0" in out


def press_hotkey(vk: int) -> None:
    """Ctrl+Alt+<vk> (RegisterHotKey sentetik girdiye de tepki verir)."""
    u32 = ctypes.windll.user32
    for k in (0x11, 0x12, vk):
        u32.keybd_event(k, 0, 0, 0)
    for k in (vk, 0x12, 0x11):
        u32.keybd_event(k, 0, 0x0002, 0)


def drag(x0: int, y0: int, x1: int, y1: int) -> None:
    u32 = ctypes.windll.user32
    u32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    u32.SetCursorPos(x0, y0)
    time.sleep(0.1)
    u32.mouse_event(0x0002, 0, 0, 0, 0)
    for i in range(1, 11):
        u32.SetCursorPos(x0 + (x1 - x0) * i // 10, y0 + (y1 - y0) * i // 10)
        time.sleep(0.03)
    u32.mouse_event(0x0004, 0, 0, 0, 0)


def test_edit_mode_moves_box_and_saves_profile(procs):
    title = "Fake Game E2E Edit"
    try:
        start_game(procs, title, "--blank")
        time.sleep(1.5)
        app = start_app(procs, title, "fixed")
        assert app.wait_for(lambda e: e["event"] == "ready", 60)
        set_clipboard("ちょっと待って！")
        ev = app.wait_for(lambda e: e["event"] == "overlay" and e["rects"], 30)
        x, y, w, h = ev["rects"][0]
        press_hotkey(ord("E"))
        on = app.wait_for(lambda e: e["event"] == "edit", 5)
        assert on and on["on"], "düzenleme moduna girilmedi"
        assert not on["exstyle"] & 0x20, "düzenleme modunda overlay hâlâ tıklamayı geçiriyor"
        time.sleep(0.3)
        drag(x + w // 2, y + h // 2, x + w // 2, y + h // 2 - 300)  # kutuyu 300 px yukarı taşı
        moved = app.wait_for(lambda e: e["event"] == "overlay" and e["rects"]
                             and e["rects"][0][1] <= y - 250, 5)
        assert moved, "düzenleme modunda kutu taşınmadı"
        press_hotkey(ord("E"))  # çıkış -> profil kaydı
        off = app.wait_for(lambda e: e["event"] == "edit", 5)
        assert off and not off["on"] and off["exstyle"] & 0x20, "normal moda dönülmedi"
        prof = Config().profile(title)
        # Varsayılan kutu istemci alanında y=518'de (720 * 0.72); 300 px yukarı taşındı.
        assert prof["box"] is not None and prof["box"][1] < 518 - 250
        assert prof["mode"] == "fixed"
        press_hotkey(ord("Q"))
        assert app.p.wait(10) == 0, "Ctrl+Alt+Q ile çıkılmadı"
    finally:
        cfg = Config()
        cfg.data["profiles"].pop(title, None)
        cfg.save()


def test_window_closed_notifies(procs):
    title = "Fake Game E2E Close"
    game = start_game(procs, title, "--blank")
    time.sleep(1.5)
    app = start_app(procs, title, "fixed")
    assert app.wait_for(lambda e: e["event"] == "started", 30)
    game.kill()
    seen = set()
    app.wait_for(lambda e: seen.add(e["event"]) or {"window_closed", "notify"} <= seen, 10)
    assert "window_closed" in seen, "pencere kapanması fark edilmedi"
    assert "notify" in seen, "bildirim gösterilmedi"
    assert app.p.poll() is None, "uygulama çöktü"


@pytest.mark.parametrize("lang", ["ko", "en"])
def test_free_mode_other_languages(procs, lang):
    if not ocr_language_available(lang):
        pytest.skip(f"Windows OCR {lang} dil paketi yok")
    title = f"Fake Game E2E Free {lang}"
    game = start_game(procs, title, "--lang", lang, "--line", "0", "--pos", "250,320", "--sizes", "30",
                      "--interval", "1000")
    line = game.wait_for(lambda e: e["event"] == "line", 15)
    assert line, "sahte oyun replik göstermedi"
    app = start_app(procs, title, "free", lang)
    ev = app.wait_for(lambda e: e["event"] == "overlay" and e["mode"] == "free"
                      and any(overlaps(r, line["rect"]) for r in e["rects"]), 90)
    assert ev, f"{lang} replik konumunda çeviri kutusu oluşmadı"


@pytest.mark.parametrize("lang,text", [("en", "Where are you going? We are not done talking."),
                                       ("ko", "어디 가? 아직 얘기 안 끝났어.")])
def test_fixed_mode_other_languages(procs, lang, text):
    title = f"Fake Game E2E Fixed {lang}"
    start_game(procs, title, "--blank")
    time.sleep(1.5)
    app = start_app(procs, title, "fixed", lang)
    assert app.wait_for(lambda e: e["event"] == "ready", 60)
    set_clipboard(text)
    ev = app.wait_for(lambda e: e["event"] == "overlay" and e["mode"] == "fixed" and e["rects"], 30)
    assert ev, f"panodaki {lang} metin kutuda çıkmadı"


def test_fixed_mode_ignores_other_language(procs):
    """Japonca profilde panoya İngilizce kopyalamak çeviri tetiklememeli."""
    title = "Fake Game E2E Fixed ignore"
    start_game(procs, title, "--blank")
    time.sleep(1.5)
    app = start_app(procs, title, "fixed", "ja")
    assert app.wait_for(lambda e: e["event"] == "ready", 60)
    set_clipboard("https://example.com this is not Japanese")
    assert not app.wait_for(lambda e: e["event"] == "overlay" and e["rects"], 4)


@pytest.mark.skipif(not japanese_ocr_available(), reason="Windows OCR Japonca dil paketi yok")
@pytest.mark.parametrize("extra", [[], ["--animate", "--blink"]], ids=["sabit", "hareketli"])
def test_click_clears_old_translation_same_place(procs, extra):
    """Görsel roman: replikler hep aynı yerde, tıklayınca ilerliyor. Eski çeviri tıklayınca
    hemen kalkmalı ve yeni replik çevrilmeli (yoksa eski kutu yeni yazıyı örter)."""
    title = "Fake Game E2E Click"
    game = start_game(procs, title, "--click-advance", "--line", "0", "--pos", "200,560",
                      "--sizes", "30", *extra)
    line = game.wait_for(lambda e: e["event"] == "line", 15)
    assert line
    app = start_app(procs, title, "free")
    assert app.wait_for(lambda e: e["event"] == "overlay" and any(overlaps(r, line["rect"]) for r in e["rects"]), 90), \
        "ilk replik çevrilmedi"
    for i in range(3):
        click(60 + 640, 60 + 200)  # oyunun boş bir yerine tıkla (yazının üstü değil)
        t0 = time.monotonic()
        cleared = app.wait_for(lambda e: e["event"] == "overlay" and e["rects"] == [], 2)
        assert cleared, f"{i + 1}. tıklamada eski çeviri silinmedi"
        assert time.monotonic() - t0 < 1.0, "silme gecikti"
        new = game.wait_for(lambda e: e["event"] == "line", 5)
        assert new and new["index"] == i + 1
        # Kutu yazıya sıkı oturur, oyunun yazı paneli ise kenar boşluklu: %30 örtüşme yeterli.
        got = app.wait_for(lambda e: e["event"] == "overlay"
                           and any(overlaps(r, new["rect"], 0.3) for r in e["rects"]), 10)
        assert got, f"{i + 1}. tıklamadan sonra yeni replik çevrilmedi"


@pytest.mark.skipif(not japanese_ocr_available(), reason="Windows OCR Japonca dil paketi yok")
def test_animated_scene_still_translated(procs):
    """Sürekli hareket eden sahnede ekran hiç durulmuyor; OCR yine de çalışmalı."""
    title = "Fake Game E2E Anim"
    game = start_game(procs, title, "--animate", "--line", "0", "--pos", "250,400", "--sizes", "30",
                      "--interval", "1000")
    line = game.wait_for(lambda e: e["event"] == "line", 15)
    app = start_app(procs, title, "free")
    assert app.wait_for(lambda e: e["event"] == "overlay"
                        and any(overlaps(r, line["rect"]) for r in e["rects"]), 90), \
        "hareketli sahnede çeviri kutusu oluşmadı"


@pytest.mark.skipif(not japanese_ocr_available(), reason="Windows OCR Japonca dil paketi yok")
@pytest.mark.parametrize("extra,region", [([], None), (["--animate"], [150, 520, 900, 120])],
                         ids=["sabit-tum-pencere", "hareketli-diyalog-alani"])
def test_slow_typewriter_translated_once(procs, extra, region):
    """Yazı yavaş akıyor ve virgülde duraksıyor: yarım metin çevrilmemeli, her replik için
    ekranda yalnızca TEK çeviri (tamamlanmış metnin) görünmeli.
    Hareketli sahnede tarama alanı diyalog kutusuyla sınırlı (Ctrl+Alt+E ile yapılan ayar):
    tüm pencere taranınca Windows OCR desenli/hareketli arka planda ara sıra sahte blok okuyor."""
    title = "Fake Game E2E Typing"
    if region:
        Config().save_profile(title, {"mode": "free", "lang": "ja", "box": None, "region": region})
    game = start_game(procs, title, "--click-advance", "--line", "0", "--pos", "200,560", "--sizes", "30",
                      "--typewriter", "--type-ms", "130", "--pause-ms", "600", *extra)
    app = start_app(procs, title, "free")
    assert app.wait_for(lambda e: e["event"] == "ready", 60)
    first = game.wait_for(lambda e: e["event"] == "line", 30)
    assert app.wait_for(lambda e: e["event"] == "overlay"
                        and any(overlaps(r, first["rect"], 0.3) for r in e["rects"]), 15)
    for i in range(2):
        list(iter_events(app))  # tıklamadan önceki (eski replik) olaylarını atla
        click(60 + 640, 60 + 200)
        assert game.wait_for(lambda e: e["event"] == "line_start", 5)
        shown, done, deadline = [], None, time.monotonic() + 20
        while time.monotonic() < deadline:  # replik bitip 3 s geçene kadar overlay'i izle
            ev = game.wait_for(lambda e: e["event"] == "line", 0.1) if done is None else None
            if ev:
                done = (ev, time.monotonic())
            for e in iter_events(app):
                if e["event"] == "overlay" and e["rects"]:
                    shown.append(e["rects"])
            if done and time.monotonic() - done[1] > 3:
                break
        assert done, "replik tamamlanmadı"
        assert len(shown) == 1, f"{i + 1}. replikte {len(shown)} farklı çeviri gösterildi (yarım metin çevrildi)"
        assert any(overlaps(r, done[0]["rect"], 0.3) for r in shown[0])


@pytest.mark.skipif(not japanese_ocr_available(), reason="Windows OCR Japonca dil paketi yok")
def test_moving_character_behind_text(procs):
    """Kullanıcının oyunu: yazının arkasında karakter hareket ediyor, yazı harf harf akıyor,
    replikler aynı yerde ve tıklayınca ilerliyor. Her replik için TEK çeviri gelmeli ve
    tıklanana kadar ekrandan kaybolmamalı (OCR gürültüsü çeviriyi düşürmemeli)."""
    title = "Fake Game E2E Behind"
    game = start_game(procs, title, "--click-advance", "--line", "0", "--pos", "200,560", "--sizes", "30",
                      "--typewriter", "--type-ms", "100", "--pause-ms", "400", "--behind")
    app = start_app(procs, title, "free")
    assert app.wait_for(lambda e: e["event"] == "ready", 60)
    for i in range(3):
        if i:
            list(iter_events(app))  # tıklamadan önceki (eski replik) olaylarını atla
            click(60 + 640, 60 + 150)
        done = game.wait_for(lambda e: e["event"] == "line", 15)
        assert done, "replik tamamlanmadı"
        shown, drops, t_end = [], 0, time.monotonic() + 6  # tamamlandıktan sonra 6 s izle
        while time.monotonic() < t_end:
            for e in iter_events(app):
                if e["event"] != "overlay":
                    continue
                if e["rects"]:
                    shown.append(e["rects"])
                elif shown:
                    drops += 1
            time.sleep(0.05)
        assert shown, f"{i + 1}. replik çevrilmedi"
        assert len(shown) == 1, f"{i + 1}. replikte {len(shown)} farklı çeviri gösterildi"
        assert drops == 0, f"{i + 1}. replikte çeviri {drops} kez kayboldu"
        assert any(overlaps(r, done["rect"], 0.3) for r in shown[0]), (shown, done["rect"])


@pytest.mark.skipif(not japanese_ocr_available(), reason="Windows OCR Japonca dil paketi yok")
def test_click_while_typing_translates_immediately(procs):
    """Yazı akarken tıklama yazının tamamını getirir: çeviri doğrulama beklemeden gelmeli."""
    title = "Fake Game E2E Complete"
    game = start_game(procs, title, "--click-advance", "--line", "0", "--pos", "200,560", "--sizes", "30",
                      "--typewriter", "--type-ms", "250", "--behind")
    app = start_app(procs, title, "free")
    assert app.wait_for(lambda e: e["event"] == "ready", 60)
    assert game.wait_for(lambda e: e["event"] == "line", 30)
    latencies = []
    for i in range(3):
        click(60 + 640, 60 + 150)          # sonraki sayfa: yazı akmaya başlar
        assert game.wait_for(lambda e: e["event"] == "line_start", 5)
        time.sleep(1.5)                    # yazının bir kısmı aksın
        click(60 + 640, 60 + 150)          # tamamla
        t0 = time.monotonic()
        line = game.wait_for(lambda e: e["event"] == "line", 3)
        assert line, "tıklama yazıyı tamamlamadı"
        got = app.wait_for(lambda e: e["event"] == "overlay"
                           and any(overlaps(r, line["rect"], 0.3) for r in e["rects"]), 5)
        assert got, f"{i + 1}. replik çevrilmedi"
        latencies.append(time.monotonic() - t0)
    print("tamamla tıkı -> çeviri (s):", [round(x, 2) for x in latencies])
    assert max(latencies) < 1.5
