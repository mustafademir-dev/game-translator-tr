"""Windows OCR testi: Japonca metni görüntüye çiz, OCR'dan geçir, karakter benzerliğini ölç.
Japonca dil paketi yoksa atlanır."""
import difflib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from src.ocr.winocr import japanese_ocr_available

pytestmark = pytest.mark.skipif(not japanese_ocr_available(),
                                reason="Windows OCR Japonca dil paketi yok")

FONT_CANDIDATES = ["C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/msgothic.ttc"]
SAMPLES = [
    "田中さん、今日は学校に来ないんですか？",
    "もう遅いから、早く帰ったほうがいいよ。",
    "この町には、昔から不思議な言い伝えがあるらしい。",
]


def jp_font(size):
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    pytest.skip("Japonca sistem fontu yok")


def render(lines, size=28, bg=(40, 50, 90), fg=(255, 255, 255)):
    img = Image.new("RGB", (900, 80 + len(lines) * 50), bg)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((40, 30 + i * (size + 14)), line, font=jp_font(size), fill=fg)
    arr = np.array(img.convert("RGBA"))
    return arr[:, :, [2, 1, 0, 3]].copy()  # RGBA -> BGRA


def similarity(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


@pytest.fixture(scope="module")
def engine():
    from src.ocr.winocr import WindowsOcrEngine
    return WindowsOcrEngine()


@pytest.mark.parametrize("text", SAMPLES)
def test_single_line_similarity(engine, text):
    blocks = engine.recognize(render([text]))
    got = "".join(b.text for b in blocks)
    score = similarity(got.replace("?", "？"), text)
    print(f"benzerlik={score:.2f}")
    assert score >= 0.8


def test_paragraph_merged_into_one_block(engine):
    blocks = engine.recognize(render(SAMPLES[:2]))
    assert len(blocks) == 1
    assert similarity(blocks[0].text.replace("?", "？"), "".join(SAMPLES[:2])) >= 0.8


def test_dark_text_on_light_background(engine):
    blocks = engine.recognize(render([SAMPLES[1]], bg=(240, 235, 220), fg=(20, 20, 20)))
    assert similarity("".join(b.text for b in blocks), SAMPLES[1]) >= 0.8


def test_block_position(engine):
    blocks = engine.recognize(render([SAMPLES[0]]))
    b = blocks[0]
    assert 30 <= b.x <= 50 and 25 <= b.y <= 50 and b.h >= 20
