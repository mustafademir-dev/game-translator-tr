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
