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
from src.ocr.winocr import japanese_ocr_available

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


def click(x: int, y: int) -> None:
    u32 = ctypes.windll.user32
    # Test süreci de fiziksel piksel kullanmalı (ekran ölçekliyse imleç kayar).
    u32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    u32.SetCursorPos(x, y)
    time.sleep(0.1)
    u32.mouse_event(0x0002, 0, 0, 0, 0)  # sol tuş bas
    u32.mouse_event(0x0004, 0, 0, 0, 0)  # bırak


@pytest.fixture
def procs():
    started: list[Proc] = []
    yield started
    for p in started:
        p.kill()


def start_game(procs, title, *extra) -> Proc:
    g = Proc(["tools/fake_game.py", "--title", title, "--at", "60,60", "--topmost", *extra])
    procs.append(g)
    return g


def start_app(procs, title, mode) -> Proc:
    a = Proc(["tests/offline_launcher.py", "--window", title, "--mode", mode, "--test-report"])
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
        time.sleep(0.5)
        drag(x + w // 2, y + h // 2, x + w // 2, y + h // 2 - 300)  # kutuyu 300 px yukarı taşı
        moved = app.wait_for(lambda e: e["event"] == "overlay" and e["rects"]
                             and e["rects"][0][1] <= y - 250, 5)
        assert moved, "düzenleme modunda kutu taşınmadı"
        press_hotkey(ord("E"))  # çıkış -> profil kaydı
        time.sleep(1.0)
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
