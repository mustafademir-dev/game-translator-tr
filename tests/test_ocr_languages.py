"""Korece ve İngilizce OCR testi: metni görüntüye çiz, OCR'dan geçir, benzerliği ölç.
Dil paketi / Paddle modeli yoksa ilgili test atlanır."""
import difflib
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from src.ocr.paddle import PADDLE_DIR
from src.ocr.winocr import ocr_language_available

SAMPLES = {
    "ko": ["다나카 씨, 오늘 학교에 안 와요?", "벌써 늦었으니까 빨리 집에 가는 게 좋아."],
    "en": ["Tanaka, aren't you coming to school today?", "It's getting late, you should head home."],
}
FONTS = {"ko": "C:/Windows/Fonts/malgun.ttf", "en": "C:/Windows/Fonts/segoeui.ttf"}


def render(lang, lines, size=28):
    if not Path(FONTS[lang]).exists():
        pytest.skip(f"{lang} sistem fontu yok")
    font = ImageFont.truetype(FONTS[lang], size)
    img = Image.new("RGB", (900, 80 + len(lines) * 50), (40, 50, 90))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((40, 30 + i * (size + 14)), line, font=font, fill=(255, 255, 255))
    return np.array(img.convert("RGBA"))[:, :, [2, 1, 0, 3]].copy()


def norm(s):
    return " ".join(s.replace("’", "'").split())


def similarity(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def windows_engine(lang):
    if not ocr_language_available(lang):
        pytest.skip(f"Windows OCR {lang} dil paketi yok")
    from src.ocr.winocr import WindowsOcrEngine
    return WindowsOcrEngine(lang)


def paddle_engine(lang):
    if importlib.util.find_spec("paddleocr") is None or not (PADDLE_DIR / lang / "rec" / "inference.pdmodel").exists():
        pytest.skip(f"PaddleOCR {lang} modeli yok (setup.py --paddle)")
    from src.ocr.paddle import PaddleOcrEngine
    return PaddleOcrEngine(lang)


@pytest.mark.parametrize("make", [windows_engine, paddle_engine], ids=["windows", "paddle"])
@pytest.mark.parametrize("lang", ["ko", "en"])
def test_paragraph_similarity(make, lang):
    engine = make(lang)
    blocks = engine.recognize(render(lang, SAMPLES[lang]))
    assert len(blocks) == 1, "iki satırlık paragraf tek blok olmalı"
    score = similarity(blocks[0].text, " ".join(SAMPLES[lang]))
    print(f"{lang} benzerlik={score:.2f}")
    assert score >= 0.85
    assert not blocks[0].vertical
