"""Uygulamayı ağ erişimi kapalıyken başlatır: her soket bağlantı denemesi hata fırlatır.

    venv\\Scripts\\python.exe tests\\offline_launcher.py [uygulama argümanları]
    venv\\Scripts\\python.exe tests\\offline_launcher.py --selfcheck   # çeviri + OCR, pencere yok
"""
from __future__ import annotations

import runpy
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ATTEMPTS: list[str] = []


def _blocked(name):
    def fn(*args, **kwargs):
        ATTEMPTS.append(name)
        raise OSError(f"ağ erişimi yasak ({name})")
    return fn


socket.socket.connect = _blocked("connect")
socket.socket.connect_ex = _blocked("connect_ex")
socket.socket.sendto = _blocked("sendto")
socket.create_connection = _blocked("create_connection")
socket.getaddrinfo = _blocked("getaddrinfo")
socket.gethostbyname = _blocked("gethostbyname")


def selfcheck() -> int:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    from src.app_env import setup_offline_env
    setup_offline_env()
    from src.config import Config
    from src.ocr.winocr import WindowsOcrEngine, japanese_ocr_available
    from src.translate import TranslationService
    from src.translate.nllb import NllbBackend

    cfg = Config()
    svc = TranslationService(NllbBackend(cfg.model_path()))
    out = svc.translate("おはようございます。")
    print("translate_ok" if out.strip() else "translate_empty", flush=True)
    if japanese_ocr_available():
        img = Image.new("RGB", (600, 100), (30, 30, 60))
        ImageDraw.Draw(img).text((20, 30), "ちょっと待って！",
                                 font=ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 30), fill=(255, 255, 255))
        arr = np.array(img.convert("RGBA"))[:, :, [2, 1, 0, 3]].copy()
        blocks = WindowsOcrEngine().recognize(arr)
        print("ocr_ok" if blocks else "ocr_empty", flush=True)
    else:
        print("ocr_skipped", flush=True)
    try:
        from src.ocr.paddle import PaddleOcrEngine
        paddle = PaddleOcrEngine()
    except Exception:
        print("paddle_skipped", flush=True)
    else:
        img = Image.new("RGB", (600, 100), (30, 30, 60))
        ImageDraw.Draw(img).text((20, 30), "ちょっと待って！",
                                 font=ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 30), fill=(255, 255, 255))
        arr = np.array(img.convert("RGBA"))[:, :, [2, 1, 0, 3]].copy()
        print("paddle_ok" if paddle.recognize(arr) else "paddle_empty", flush=True)
    print(f"network_attempts={len(ATTEMPTS)}", flush=True)
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selfcheck"]:
        sys.exit(selfcheck())
    sys.argv = ["src.app", *sys.argv[1:]]
    runpy.run_module("src.app", run_name="__main__", alter_sys=True)
