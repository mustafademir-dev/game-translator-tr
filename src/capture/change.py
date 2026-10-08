"""Değişim tespiti ve stabilizasyon (serbest konum modu, bkz. SPEC 5.2)."""
from __future__ import annotations

import numpy as np


def small_gray(bgra: np.ndarray, step: int = 2) -> np.ndarray:
    """Küçültülmüş gri kopya (her `step` pikselden biri)."""
    s = bgra[::step, ::step, :3].astype(np.uint16)
    return ((s[:, :, 0] + 2 * s[:, :, 1] + s[:, :, 2]) // 4).astype(np.int16)


class ChangeDetector:
    """Her kareyi bir öncekiyle karşılaştırır; değişim durup `stable_ms` boyunca
    sabit kalınca bir kez True döner. Fark eşiğin altındaysa hiçbir şey olmaz."""

    def __init__(self, pixel_threshold: int = 30, min_pixels: int = 6, stable_ms: int = 400):
        self.pixel_threshold = pixel_threshold
        self.min_pixels = min_pixels
        self.stable_ms = stable_ms
        self._prev: np.ndarray | None = None
        self._pending = True          # ilk kare de OCR'a gider
        self._last_change = 0.0

    def reset(self) -> None:
        self._prev = None
        self._pending = True

    def changed_pixels(self, a: np.ndarray, b: np.ndarray) -> int:
        if a.shape != b.shape:
            return a.size
        return int(np.count_nonzero(np.abs(a - b) > self.pixel_threshold))

    def feed(self, small: np.ndarray, now_ms: float) -> bool:
        """`small`: small_gray() çıktısı. True: şimdi OCR çalıştır."""
        prev, self._prev = self._prev, small
        if prev is None:
            self._last_change = now_ms
            self._pending = True
            return False
        if self.changed_pixels(prev, small) >= self.min_pixels:
            self._last_change = now_ms
            self._pending = True
            return False
        if self._pending and now_ms - self._last_change >= self.stable_ms:
            self._pending = False
            return True
        return False
