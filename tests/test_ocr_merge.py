from src.ocr import TextBlock, merge_lines


def tb(text, x, y, w, h, vertical=False):
    return TextBlock(text, x, y, w, h, vertical)


def test_paragraph_lines_merged():
    lines = [tb("今日はいい天気ですね。", 100, 500, 400, 30),
             tb("散歩に行きましょう。", 100, 538, 360, 30)]
    out = merge_lines(lines)
    assert len(out) == 1
    b = out[0]
    assert b.text == "今日はいい天気ですね。散歩に行きましょう。"
    assert (b.x, b.y, b.w, b.h) == (100, 500, 400, 68)


def test_same_row_fragments_joined_in_x_order():
    lines = [tb("今日は学校に来ないんですか？", 153, 37, 400, 23), tb("田中さん、", 22, 38, 120, 22)]
    out = merge_lines(lines)
    assert [b.text for b in out] == ["田中さん、今日は学校に来ないんですか？"]


def test_far_blocks_stay_separate():
    lines = [tb("こんにちは", 50, 50, 200, 30), tb("さようなら", 600, 400, 200, 30)]
    assert len(merge_lines(lines)) == 2


def test_different_font_size_not_merged():
    lines = [tb("タイトル", 100, 100, 300, 60), tb("本文です", 100, 165, 200, 20)]
    assert len(merge_lines(lines)) == 2


def test_non_japanese_dropped():
    lines = [tb("HP 100/100", 10, 10, 120, 20), tb("はい", 300, 300, 60, 30), tb("   ", 0, 0, 5, 5)]
    out = merge_lines(lines)
    assert [b.text for b in out] == ["はい"]


def test_vertical_columns_right_to_left():
    cols = [tb("いいえ", 100, 50, 30, 120, True), tb("はい", 140, 50, 30, 90, True)]
    out = merge_lines(cols)
    assert len(out) == 1 and out[0].vertical
    assert out[0].text == "はいいいえ"
    assert (out[0].x, out[0].w) == (100, 70)


def test_english_lines_joined_with_space_and_numbers_dropped():
    lines = [tb("Where are you", 100, 500, 300, 30), tb("going?", 100, 538, 120, 30),
             tb("100/100", 900, 20, 80, 20)]
    out = merge_lines(lines, "en")
    assert [b.text for b in out] == ["Where are you going?"]


def test_korean_never_vertical_and_filtered():
    lines = [tb("잠깐만", 100, 100, 30, 120, True), tb("こんにちは", 300, 300, 200, 30)]
    out = merge_lines(lines, "ko")
    assert [(b.text, b.vertical) for b in out] == [("잠깐만", False)]


def test_wide_line_spacing_and_short_hiragana_line_still_one_paragraph():
    """Geniş satır aralığı + yalnızca hiragana olan kısa satır (OCR kutusu daha kısa ölçülür)."""
    lines = [tb("今日は学校に行かないの？", 100, 500, 400, 32),
             tb("ずっと待ってたのに", 100, 572, 300, 22)]   # aralık 40 px (~1.25 satır), yükseklik 22/32
    assert len(merge_lines(lines)) == 1


def test_merge_all_reading_order():
    from src.ocr.merge import merge_all
    blocks = [tb("ずっと待ってたのに", 100, 600, 300, 30), tb("今日は来ないの？", 100, 500, 300, 30)]
    out = merge_all(blocks, "ja")
    assert [b.text for b in out] == ["今日は来ないの？ずっと待ってたのに"]
    assert merge_all([tb("Hi", 0, 0, 10, 10), tb("there", 0, 20, 10, 10)], "en")[0].text == "Hi there"
