"""OCR arayüzü."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class TextBlock:
    text: str
    x: int
    y: int
    w: int
    h: int
    vertical: bool = False


class OcrEngine(Protocol):
    def recognize(self, image: np.ndarray) -> list[TextBlock]:
        """`image`: HxWx4 BGRA uint8 (mss çıktısı). Koordinatlar görüntüye göredir."""
        ...


class OcrUnavailableError(RuntimeError):
    pass
