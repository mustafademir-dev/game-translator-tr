"""Ayar dosyası (settings.json) ve pencere başlığına göre profiller.

Diske yazılan tek şey bu dosyadır; içinde kullanıcı metni bulunmaz.
"""
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "settings.json"
DICTIONARY_PATH = ROOT / "dictionary.json"
FONT_PATH = ROOT / "assets" / "NotoSans.ttf"

DEFAULTS: dict = {
    "model": "1.3B",
    "model_dir": "models/nllb-1.3B-ct2-int8",
    "threads": 0,            # 0 = çekirdek sayısının yarısı
    "beam_size": 2,
    "pivot": False,
    "ocr_engine": "windows",  # "windows" | "paddle"
    "capture_fps": 5,
    # Değişim eşiği: küçültülmüş gri karede |fark| > diff_pixel_threshold olan
    # piksel sayısı diff_min_pixels'ten azsa "değişim yok" sayılır.
    "diff_pixel_threshold": 30,
    "diff_min_pixels": 6,
    "stable_ms": 400,
    "font_max_px": 28,
    "font_min_px": 12,
    "hotkeys": {
        "toggle": "Ctrl+Alt+T",
        "retranslate": "Ctrl+Alt+R",
        "edit": "Ctrl+Alt+E",
        "mode": "Ctrl+Alt+M",
        "debug": "Ctrl+Alt+D",
        "quit": "Ctrl+Alt+Q",
    },
    # Pencere başlığı -> {"mode": "fixed"|"free", "box": [x,y,w,h]|None, "region": [x,y,w,h]|None}
    # Koordinatlar oyun penceresinin istemci alanının sol üstüne göre fiziksel pikseldir.
    "profiles": {},
}

DEFAULT_PROFILE = {"mode": "fixed", "box": None, "region": None}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "profiles":
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, path: Path = SETTINGS_PATH):
        self.path = path
        self._lock = threading.Lock()
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
        self.data = _merge(DEFAULTS, data)

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value
        self.save()

    def model_path(self) -> Path:
        p = Path(self.data["model_dir"])
        return p if p.is_absolute() else ROOT / p

    def profile(self, title: str) -> dict:
        prof = self.data["profiles"].get(title, {})
        return {**DEFAULT_PROFILE, **prof}

    def save_profile(self, title: str, profile: dict) -> None:
        self.data["profiles"][title] = profile
        self.save()

    def save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
