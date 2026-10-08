"""Windows dahili OCR (Windows.Media.Ocr), Japonca. Ağ kullanmaz."""
from __future__ import annotations

import time

import numpy as np

from ..translate.text import contains_japanese
from .base import OcrUnavailableError, TextBlock
from .merge import merge_lines

OCR_CAPABILITY_CMD = 'Add-WindowsCapability -Online -Name "Language.OCR~~~ja-JP~0.0.1.0"'


def japanese_ocr_available() -> bool:
    try:
        from winsdk.windows.media.ocr import OcrEngine as _Engine
        return any(l.language_tag.lower().startswith("ja") for l in _Engine.available_recognizer_languages)
    except Exception:
        return False


def _join_words(words: list[str]) -> str:
    """Windows OCR Japonca karakterleri boşlukla ayırır; boşluğu yalnızca Latin kelimeler arasında tut."""
    out = ""
    for w in words:
        if out and not (contains_japanese(out[-1]) or contains_japanese(w[0])):
            out += " "
        out += w
    return out


class WindowsOcrEngine:
    # Küçük yazıda tanıma zayıf; bu yükseklikten küçük görüntüler büyütülür.
    MIN_UPSCALE_HEIGHT = 400

    def __init__(self):
        if not japanese_ocr_available():
            raise OcrUnavailableError("Windows OCR Japonca dil paketi yok")
        from winsdk.windows.globalization import Language
        from winsdk.windows.media.ocr import OcrEngine as _Engine
        self._engine = _Engine.try_create_from_language(Language("ja"))
        if self._engine is None:
            raise OcrUnavailableError("Windows OCR Japonca motoru oluşturulamadı")
        self._max_dim = int(_Engine.max_image_dimension)

    def _to_bitmap(self, bgra: np.ndarray):
        from winsdk.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
        from winsdk.windows.storage.streams import DataWriter
        h, w = bgra.shape[:2]
        writer = DataWriter()
        writer.write_bytes(np.ascontiguousarray(bgra).tobytes())
        return SoftwareBitmap.create_copy_from_buffer(
            writer.detach_buffer(), BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.PREMULTIPLIED)

    @staticmethod
    def _wait(op, timeout: float = 10.0):
        # asyncio kullanılmaz: Windows'ta olay döngüsü kendi içinde yerel soket açar.
        from winsdk.windows.foundation import AsyncStatus
        deadline = time.monotonic() + timeout
        while op.status == AsyncStatus.STARTED:
            if time.monotonic() > deadline:
                op.cancel()
                raise TimeoutError("Windows OCR zaman aşımı")
            time.sleep(0.002)
        if op.status != AsyncStatus.COMPLETED:
            raise RuntimeError("Windows OCR başarısız")
        return op.get_results()

    def recognize(self, image: np.ndarray) -> list[TextBlock]:
        img = image
        if img.shape[2] == 3:
            img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
        scale = 1
        if img.shape[0] < self.MIN_UPSCALE_HEIGHT and max(img.shape[:2]) * 2 <= self._max_dim:
            scale = 2
            img = img.repeat(2, axis=0).repeat(2, axis=1)
        if max(img.shape[:2]) > self._max_dim:
            raise ValueError("Görüntü Windows OCR için fazla büyük")
        bitmap = self._to_bitmap(img)

        result = self._wait(self._engine.recognize_async(bitmap))
        lines: list[TextBlock] = []
        for line in result.lines:
            words = list(line.words)
            if not words:
                continue
            rects = [w.bounding_rect for w in words]
            x0 = min(r.x for r in rects)
            y0 = min(r.y for r in rects)
            x1 = max(r.x + r.width for r in rects)
            y1 = max(r.y + r.height for r in rects)
            w, h = (x1 - x0) / scale, (y1 - y0) / scale
            text = _join_words([wd.text for wd in words])
            vertical = len(text) > 1 and h > 2 * w
            lines.append(TextBlock(text, int(x0 / scale), int(y0 / scale), int(round(w)), int(round(h)), vertical))
        return merge_lines(lines)
