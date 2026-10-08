"""Ekran yakalama (mss, GDI). Görüntü yalnızca bellekte tutulur."""
from __future__ import annotations

import numpy as np


class Grabber:
    """mss nesnesi oluşturulduğu thread'de kullanılmalıdır."""

    def __init__(self):
        import mss
        self._sct = mss.mss()

    def grab(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        shot = self._sct.grab({"left": x, "top": y, "width": w, "height": h})
        return np.asarray(shot)  # HxWx4 BGRA

    def close(self) -> None:
        self._sct.close()


def edge_color(img: np.ndarray, x: int, y: int, w: int, h: int, border: int = 2) -> tuple[int, int, int]:
    """Bölgenin kenar piksellerinin ortalama rengi (R, G, B)."""
    H, W = img.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return (0, 0, 0)
    reg = img[y0:y1, x0:x1, :3].astype(np.float64)
    b = max(1, min(border, (y1 - y0) // 2, (x1 - x0) // 2))
    parts = [reg[:b].reshape(-1, 3), reg[-b:].reshape(-1, 3),
             reg[:, :b].reshape(-1, 3), reg[:, -b:].reshape(-1, 3)]
    mean = np.concatenate(parts).mean(axis=0)
    return int(mean[2]), int(mean[1]), int(mean[0])


def text_color_for(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = bg
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return (0, 0, 0) if lum > 140 else (255, 255, 255)
