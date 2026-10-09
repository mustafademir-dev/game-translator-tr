from .base import OcrEngine, OcrUnavailableError, TextBlock
from .merge import merge_lines


def create_engine(name: str, lang: str = "ja") -> OcrEngine:
    if name == "manga":
        from .manga import MangaOcrEngine
        return MangaOcrEngine(lang)
    if name == "paddle":
        from .paddle import PaddleOcrEngine
        return PaddleOcrEngine(lang)
    from .winocr import WindowsOcrEngine
    return WindowsOcrEngine(lang)


__all__ = ["OcrEngine", "OcrUnavailableError", "TextBlock", "merge_lines", "create_engine"]
