"""Manga OCR: balon gruplama (model gerektirmez)."""
from src.ocr.manga import _postprocess, cluster_boxes


def test_columns_of_one_bubble_merge_but_far_bubbles_stay_apart():
    bubble1 = [(100, 100, 24, 200), (130, 100, 24, 180), (160, 105, 10, 60)]  # 2 sütun + furigana
    bubble2 = [(400, 120, 24, 150)]                                            # uzaktaki balon
    out = sorted(cluster_boxes(bubble1 + bubble2))
    assert len(out) == 2
    assert out[0] == (100, 100, 70, 200)


def test_no_chain_merging_across_page():
    # Aralıklı küçük kutular zincir oluşturup tüm sayfayı tek bölge yapmamalı.
    chain = [(i * 60, 300, 20, 20) for i in range(10)]
    assert len(cluster_boxes(chain)) == 10


def test_postprocess_like_manga_ocr():
    assert _postprocess("お 前 ら さ ! …") == "お前らさ！．．．"  # manga-ocr gibi: tam genişlik
