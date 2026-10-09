"""Değişim tespiti ve stabilizasyon (serbest konum modu, bkz. SPEC 5.2)."""
from __future__ import annotations

import numpy as np


def small_gray(bgra: np.ndarray, step: int = 2) -> np.ndarray:
    """Küçültülmüş gri kopya (her `step` pikselden biri)."""
    s = bgra[::step, ::step, :3].astype(np.uint16)
    return ((s[:, :, 0] + 2 * s[:, :, 1] + s[:, :, 2]) // 4).astype(np.int16)


class ChangeDetector:
    """Her kareyi bir öncekiyle karşılaştırır; değişim durup `stable_ms` boyunca
    sabit kalınca bir kez True döner. Fark eşiğin altındaysa hiçbir şey olmaz.

    Ekran hiç durulmuyorsa (hareketli arka plan, efekt, animasyon) en geç `max_wait_ms`
    sonra yine True döner; yoksa böyle sahnelerde OCR hiç çalışmaz."""

    def __init__(self, pixel_threshold: int = 30, min_pixels: int = 6, stable_ms: int = 400,
                 max_wait_ms: int = 1500):
        self.pixel_threshold = pixel_threshold
        self.min_pixels = min_pixels
        self.stable_ms = stable_ms
        self.max_wait_ms = max_wait_ms
        self._prev: np.ndarray | None = None
        self._pending = True          # ilk kare de OCR'a gider
        self._last_change = 0.0
        self._wait_start: float | None = None  # bekleyen değişimin başladığı an

    def reset(self) -> None:
        """Bir sonraki sabit karede (ya da en geç max_wait_ms sonra) OCR çalışsın."""
        self._prev = None
        self._pending = True
        self._wait_start = None

    def changed_pixels(self, a: np.ndarray, b: np.ndarray) -> int:
        if a.shape != b.shape:
            return a.size
        return int(np.count_nonzero(np.abs(a - b) > self.pixel_threshold))

    def _fire(self) -> bool:
        self._pending = False
        self._wait_start = None
        return True

    def feed(self, small: np.ndarray, now_ms: float) -> bool:
        """`small`: small_gray() çıktısı. True: şimdi OCR çalıştır."""
        prev, self._prev = self._prev, small
        changed = prev is None or self.changed_pixels(prev, small) >= self.min_pixels
        if changed:
            self._last_change = now_ms
            self._pending = True
        if not self._pending:
            return False
        if self._wait_start is None:
            self._wait_start = now_ms
        if not changed and now_ms - self._last_change >= self.stable_ms:
            return self._fire()
        if now_ms - self._wait_start >= self.max_wait_ms:
            return self._fire()
        return False
