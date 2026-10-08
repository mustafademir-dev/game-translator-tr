from .base import OcrEngine, OcrUnavailableError, TextBlock
from .merge import merge_lines


def create_engine(name: str) -> OcrEngine:
    if name == "paddle":
        from .paddle import PaddleOcrEngine
        return PaddleOcrEngine()
    from .winocr import WindowsOcrEngine
    return WindowsOcrEngine()


__all__ = ["OcrEngine", "OcrUnavailableError", "TextBlock", "merge_lines", "create_engine"]
