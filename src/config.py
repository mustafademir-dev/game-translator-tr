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
    # Japonca çeviri: "sugoi" = Sugoi (ja→en) + NLLB (en→tr), çok daha anlamlı; model yoksa
    # otomatik NLLB'ye düşer. "nllb" = NLLB doğrudan (ja→tr).
    "ja_model": "sugoi",
    "sugoi_dir": "models/sugoi-v4-ja-en-ct2",
    "sugoi_compute": "int16",
    # İngilizce → Türkçe (Japonca zincirinin 2. adımı ve İngilizce oyunlar): "opus" = opus-mt-tc-big-en-tr,
    # NLLB'den ~4-5 kat hızlı; model yoksa otomatik NLLB. "nllb" = her zaman NLLB.
    "en_tr_model": "opus",
    "opus_dir": "models/opus-mt-tc-big-en-tr-ct2-int8",  # int8 bu modelde çeviriyi bozuyor; int16 float32 kadar doğru, 2.4 kat hızlı
    "ocr_engine": "windows",  # "windows" | "paddle"
    # Resim modu OCR'ı: "" = otomatik (Japonca + manga-ocr kuruluysa "manga", değilse ocr_engine).
    "image_ocr_engine": "",
    "capture_fps": 10,
    # Değişim eşiği: küçültülmüş gri karede |fark| > diff_pixel_threshold olan
    # piksel sayısı diff_min_pixels'ten azsa "değişim yok" sayılır.
    "diff_pixel_threshold": 30,
    "diff_min_pixels": 6,
    "stable_ms": 400,
    # Ekran hiç durulmasa da (hareketli karakter/arka plan) en geç bu sürede bir OCR. Yarım
    # metin çevrilmez: metin düzeyindeki doğrulama (ocr/stabilize.py) bunu ayrıca engeller.
    "max_wait_ms": 300,
    "confirm_ms": 250,        # metni doğrulamak için ikinci okuma bu kadar sonra
    "clear_on_click": True,
    # Tarama alanı sınırlıyken (Ctrl+Alt+E) alandaki tüm yazıyı tek replik olarak çevir.
    "region_single_block": True,
    # Yazı akarken tıklanınca oyunlar yazının tamamını getirir; bu kadar ms sonra okunup
    # doğrulama beklemeden çevrilir.
    "complete_click_ms": 120,   # serbest modda oyuna tıklayınca / Enter / Boşluk: çeviriyi sil
    "font_max_px": 28,
    "font_min_px": 12,
    # Görünüm (Ctrl+Alt+S ayarlar penceresinden değiştirilebilir)
    "font_family": "",        # "" = uygulamayla gelen Noto Sans
    "font_bold": False,
    "text_color": "auto",     # "auto" (arka plana göre) | "white" | "black"
    "box_opacity": 100,       # kutu opaklığı, % (100 = orijinal yazı tamamen örtülür)
    "follow_original": True,  # serbest mod: çeviri yazısı orijinal yazıdan büyük olmasın
    "hotkeys": {
        "toggle": "Ctrl+Alt+T",
        "retranslate": "Ctrl+Alt+R",
        "edit": "Ctrl+Alt+E",
        "mode": "Ctrl+Alt+M",
        "debug": "Ctrl+Alt+D",
        "quit": "Ctrl+Alt+Q",
        "settings": "Ctrl+Alt+S",
    },
    # Pencere başlığı -> {"mode": "fixed"|"free", "lang": "ja"|"ko"|"en",
    #                     "box": [x,y,w,h]|None, "region": [x,y,w,h]|None}
    # Koordinatlar oyun penceresinin istemci alanının sol üstüne göre fiziksel pikseldir.
    "profiles": {},
}

# Varsayılan mod serbest konum: Textractor gerektirmeden çalışır.
DEFAULT_PROFILE = {"mode": "free", "lang": "ja", "box": None, "region": None}


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

    def opus_path(self) -> Path:
        p = Path(self.data["opus_dir"])
        return p if p.is_absolute() else ROOT / p

    def sugoi_path(self) -> Path:
        p = Path(self.data["sugoi_dir"])
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
