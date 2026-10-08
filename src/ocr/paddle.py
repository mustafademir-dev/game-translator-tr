"""PaddleOCR Japonca motoru (isteğe bağlı: `setup.py --paddle`).

Modeller kurulumda `models/paddle/` altına indirilir; çalışırken yalnızca oradan okunur.
"""
from __future__ import annotations

import numpy as np

from ..config import ROOT
from .base import OcrUnavailableError, TextBlock
from .merge import merge_lines

PADDLE_DIR = ROOT / "models" / "paddle"


class PaddleOcrEngine:
    def __init__(self):
        for sub in ("det", "rec"):
            if not (PADDLE_DIR / sub).exists():
                raise OcrUnavailableError("PaddleOCR modelleri yok (setup.py --paddle)")
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            raise OcrUnavailableError("PaddleOCR kurulu değil (setup.py --paddle)") from e
        self._ocr = PaddleOCR(
            lang="japan", use_angle_cls=False, use_gpu=False, show_log=False,
            det_model_dir=str(PADDLE_DIR / "det"), rec_model_dir=str(PADDLE_DIR / "rec"),
            cls_model_dir=str(PADDLE_DIR / "cls"),
        )

    def recognize(self, image: np.ndarray) -> list[TextBlock]:
        bgr = np.ascontiguousarray(image[:, :, :3])
        result = self._ocr.ocr(bgr, cls=False) or []
        lines: list[TextBlock] = []
        for page in result:
            for box, (text, _conf) in page or []:
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                x, y = int(min(xs)), int(min(ys))
                w, h = int(max(xs)) - x, int(max(ys)) - y
                lines.append(TextBlock(text, x, y, w, h, vertical=len(text) > 1 and h > 2 * w))
        return merge_lines(lines)
