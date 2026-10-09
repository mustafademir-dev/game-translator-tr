"""PaddleOCR motoru: Japonca, Korece, İngilizce (isteğe bağlı: `setup.py --paddle`).

Modeller kurulumda `models/paddle/<dil>/{det,rec,cls}` altına indirilir; çalışırken
yalnızca oradan okunur.
"""
from __future__ import annotations

import os

import numpy as np

from ..config import ROOT
from ..translate.text import DEFAULT_LANG, LANGS
from .base import OcrUnavailableError, TextBlock
from .merge import merge_lines

PADDLE_DIR = ROOT / "models" / "paddle"


def paddle_model_dir(lang: str) -> str:
    """Proje köküne göreli yol: Paddle ASCII dışı mutlak yolları (ör. "Masaüstü") açamıyor."""
    return f"models/paddle/{lang}"


class PaddleOcrEngine:
    def __init__(self, lang: str = DEFAULT_LANG):
        self.lang = lang
        rel = paddle_model_dir(lang)
        # Klasör değil model dosyası aranır: yarım kalmış bir indirme klasörü oluşturur ve
        # PaddleOCR eksik modeli çalışırken internetten indirmeye kalkar (offline kuralı).
        for sub in ("det", "rec"):
            if not (ROOT / rel / sub / "inference.pdmodel").exists():
                raise OcrUnavailableError(f"PaddleOCR {LANGS[lang].name} modelleri yok (setup.py --paddle)")
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            raise OcrUnavailableError("PaddleOCR kurulu değil (setup.py --paddle)") from e
        # Modeller proje köküne göreli yolla, motor oluşturulurken bir kez yüklenir.
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            self._ocr = PaddleOCR(
                lang=LANGS[lang].paddle, use_angle_cls=False, use_gpu=False, show_log=False,
                det_model_dir=f"{rel}/det", rec_model_dir=f"{rel}/rec", cls_model_dir=f"{rel}/cls",
            )
        finally:
            os.chdir(cwd)
        # İlk çağrı çok yavaş (~10 s); ilk replik kaçmasın diye şimdi ısıt.
        self._ocr.ocr(np.full((64, 256, 3), 128, np.uint8), cls=False)

    def recognize(self, image: np.ndarray) -> list[TextBlock]:
        bgr = np.ascontiguousarray(image[:, :, :3])
        result = self._ocr.ocr(bgr, cls=False) or []
        can_be_vertical = LANGS[self.lang].vertical
        lines: list[TextBlock] = []
        for page in result:
            for box, (text, _conf) in page or []:
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                x, y = int(min(xs)), int(min(ys))
                w, h = int(max(xs)) - x, int(max(ys)) - y
                lines.append(TextBlock(text, x, y, w, h,
                                       vertical=can_be_vertical and len(text) > 1 and h > 2 * w))
        return merge_lines(lines, self.lang)
