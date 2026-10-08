from PyQt6.QtGui import QFontMetrics

from src.overlay.fit import PADDING, fit_text, make_font, wrap


def test_short_text_uses_max_size(font_family):
    r = fit_text("Merhaba", 400, 60, font_family, 28, 12)
    assert r.px == 28 and r.lines == ["Merhaba"] and r.height == 60


def test_shrinks_to_fit(font_family):
    text = "Bugün okula gelmeyecek misin Tanaka? Öğretmen seni soruyordu."
    r = fit_text(text, 300, 70, font_family, 28, 12)
    assert 12 <= r.px < 28
    assert r.line_height * len(r.lines) <= 70 - 2 * PADDING
    fm = QFontMetrics(make_font(font_family, r.px))
    assert all(fm.horizontalAdvance(l) <= 300 - 2 * PADDING for l in r.lines)
    assert " ".join(r.lines) == text


def test_grows_down_below_min(font_family):
    text = "çok uzun bir metin " * 20
    r = fit_text(text, 200, 30, font_family, 28, 12)
    assert r.px == 12
    assert r.height > 30
    assert r.height == r.line_height * len(r.lines) + 2 * PADDING


def test_long_word_broken(font_family):
    fm = QFontMetrics(make_font(font_family, 20))
    lines = wrap("Aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", fm, 80)
    assert len(lines) > 1
    assert "".join(lines) == "Aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert all(fm.horizontalAdvance(l) <= 80 for l in lines)


def test_turkish_glyphs_supported(font_family):
    from PyQt6.QtGui import QFontInfo, QRawFont
    raw = QRawFont.fromFont(make_font(font_family, 20))
    assert all(raw.supportsCharacter(c) for c in "çğıİöşüÇĞÖŞÜ")
