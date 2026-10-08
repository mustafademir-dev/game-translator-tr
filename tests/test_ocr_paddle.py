"""PaddleOCR testi (isteğe bağlı kurulum: setup.py --paddle). Kurulu değilse atlanır."""
import difflib

import numpy as np
import pytest
from PIL import Image, ImageDraw

from src.ocr.paddle import PADDLE_DIR
from test_ocr_windows import SAMPLES, jp_font, render

pytest.importorskip("paddleocr")
pytestmark = pytest.mark.skipif(not (PADDLE_DIR / "rec").exists(), reason="PaddleOCR modelleri yok")


@pytest.fixture(scope="module")
def engine():
    from src.ocr.paddle import PaddleOcrEngine
    return PaddleOcrEngine()


def render_vertical(text, size=30):
    img = Image.new("RGB", (200, 80 + len(text) * (size + 6)), (40, 50, 90))
    d = ImageDraw.Draw(img)
    for i, ch in enumerate(text):
        d.text((80, 30 + i * (size + 6)), ch, font=jp_font(size), fill=(255, 255, 255))
    return np.array(img.convert("RGBA"))[:, :, [2, 1, 0, 3]].copy()


def test_horizontal_similarity(engine):
    got = "".join(b.text for b in engine.recognize(render([SAMPLES[0]])))
    score = difflib.SequenceMatcher(None, got.replace("?", "？").replace(",", "、"), SAMPLES[0]).ratio()
    print(f"benzerlik={score:.2f}")
    assert score >= 0.7


def test_vertical_text(engine):
    text = "放課後屋上に来てください"
    blocks = engine.recognize(render_vertical(text))
    assert blocks and blocks[0].vertical
    score = difflib.SequenceMatcher(None, "".join(b.text for b in blocks), text).ratio()
    print(f"dikey benzerlik={score:.2f}")
    assert score >= 0.6
