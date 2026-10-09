from src.ocr import TextBlock
from src.ocr.stabilize import TextStabilizer

FULL = "田中さん、今日は学校に来ないんですか？"


def b(text, x=100, y=500, w=None, h=30):
    return TextBlock(text, x, y, w or 20 * max(1, len(text)), h)


def texts(blocks):
    return [x.text for x in blocks]


def shown_after(s, reads):
    return [texts(s.feed(r)[0]) for r in reads]


def test_typewriter_translated_once_when_complete():
    s = TextStabilizer()
    outs = [s.feed([b(FULL[:n])]) for n in (4, 9, 14, len(FULL))]  # yazı akıyor
    assert all(shown == [] and recheck for shown, recheck in outs)  # yarım metin çevrilmez
    shown, recheck = s.feed([b(FULL)])  # ikinci kez aynı: tamamlandı
    assert texts(shown) == [FULL] and not recheck


def test_first_read_waits_for_confirmation():
    s = TextStabilizer()
    assert s.feed([b("はい、そうです")]) == ([], True)
    assert texts(s.feed([b("はい、そうです")])[0]) == ["はい、そうです"]


def test_noisy_reads_behind_moving_character_still_confirmed():
    """Yazının arkasında karakter hareket ediyor: OCR her okumada bir harfi farklı okuyor."""
    s = TextStabilizer()
    noisy = [FULL, FULL.replace("学", "字"), FULL.replace("今", "令"), FULL.replace("来", "米")]
    out = shown_after(s, [[b(t)] for t in noisy])
    assert out[0] == [] and out[1] != []  # ikinci okumada onaylandı (≥%80 benzer, uzamıyor)


def test_shown_text_is_sticky_against_noise():
    """Gösterilen çeviri tek harflik okuma farklarıyla değişmez / yeniden çevrilmez."""
    s = TextStabilizer()
    s.feed([b(FULL)])
    s.feed([b(FULL)])
    for noisy in (FULL.replace("学", "字"), FULL[:-1], FULL.replace("今", "令")):
        shown, _ = s.feed([b(noisy)])
        assert texts(shown) == [FULL]


def test_single_missed_read_does_not_remove_translation():
    s = TextStabilizer(max_misses=2)  # (varsayılan 3)
    s.feed([b(FULL)])
    s.feed([b(FULL)])
    shown, recheck = s.feed([])  # OCR bu sefer yazıyı kaçırdı
    assert texts(shown) == [FULL] and recheck  # yerinde kalır, kısa süre sonra yeniden okunur
    assert texts(s.feed([b(FULL)])[0]) == [FULL]
    s.feed([])
    assert s.feed([])[0] == []  # art arda iki okumada yoksa kalkar


def test_new_line_same_place_replaces_when_confirmed():
    s = TextStabilizer()
    s.feed([b(FULL)])
    s.feed([b(FULL)])
    other = "もう遅いから、早く帰ったほうがいいよ。"
    shown, recheck = s.feed([b(other)])
    assert texts(shown) == [FULL] and recheck  # tek okuma yetmez: bozuk okuma olabilir
    assert texts(s.feed([b(other)])[0]) == [other]  # doğrulandı: yeni çeviri


def test_one_garbled_read_of_short_line_does_not_drop_it():
    """Kısa replik + üstünden geçen karakter: tek bir çok bozuk okuma çeviriyi düşürmemeli."""
    s = TextStabilizer()
    short = "ちょっと待って！"
    s.feed([b(short)])
    s.feed([b(short)])
    for garbled in ("ちよっ一ノ待", short, "ミちょ待っ", short):
        assert texts(s.feed([b(garbled)])[0]) == [short]


def test_partially_accepted_line_upgrades_when_it_grows():
    """Yazı uzun duraksadı ve yarısı kabul edildi; devamı gelince uzun hali gösterilir."""
    s = TextStabilizer()
    half = FULL[:9]
    s.feed([b(half)])
    assert texts(s.feed([b(half)])[0]) == [half]
    assert texts(s.feed([b(FULL)])[0]) == [half]  # uzun hali onay bekler, eskisi kalır
    assert texts(s.feed([b(FULL)])[0]) == [FULL]


def test_random_junk_from_background_never_shown():
    """Hareketli karakterden çıkan sahte 'yazılar' her okumada başka: hiç onaylanmaz."""
    s = TextStabilizer()
    junk = ["ノ一", "ミ", "ヘム", "ニノ", "ハ", "一ノミ", "ヘ", "ム二"]
    assert all(out == [] for out in shown_after(s, [[b(j, x=700, y=100)] for j in junk]))


def test_noise_without_growth_accepted_after_max_rounds():
    """İki okuma hiç %80 benzer çıkmasa da (yoğun gürültü) metin uzamıyorsa sonunda kabul."""
    s = TextStabilizer(max_rounds=3)
    reads = ["今日は晴れですね", "令日は暗れですわ", "今目は睛れでずね", "今日は晴わですぬ", "今日は晴れでずね"]
    out = shown_after(s, [[b(t)] for t in reads])
    assert any(out)  # sonsuza dek beklemez


def test_reset_forgets_previous_scene():
    s = TextStabilizer()
    s.feed([b(FULL)])
    s.feed([b(FULL)])
    s.reset()
    assert s.feed([b(FULL)]) == ([], True)


def test_completes_detects_click_to_finish_text():
    from src.ocr.stabilize import completes
    assert completes(FULL[:7], FULL)                      # yarım metnin devamı
    assert completes(FULL[:7].replace("中", "申"), FULL)   # OCR gürültüsüyle de
    assert not completes(FULL[:7], "もう遅いから、早く帰ったほうがいいよ。")  # başka sayfa
    assert not completes(FULL, FULL[:7])                  # kısalmış: tamamlanma değil
    assert not completes("", FULL)


def test_show_now_skips_confirmation_and_stays_sticky():
    s = TextStabilizer()
    s.feed([b(FULL[:7])])  # yazı akıyor
    shown = s.show_now([b(FULL)])  # tıklandı, tamamı geldi
    assert texts(shown) == [FULL]
    assert texts(s.feed([b(FULL.replace("学", "字"))])[0]) == [FULL]  # sonra gürültüyle değişmez


def test_pause_at_comma_needs_extra_confirmation():
    """Yazma efekti 、 işaretinde duraksıyor: yarım metin iki okumada aynı ama cümle sonu yok."""
    from src.translate.text import looks_complete
    s = TextStabilizer(looks_complete=lambda t: looks_complete(t, "ja"))
    part = "田中さん、"
    assert s.feed([b(part)])[0] == []
    assert s.feed([b(part)])[0] == []          # iki okuma aynı ama "、" ile bitiyor: bekle
    assert s.feed([b(FULL)])[0] == []          # duraklama bitti, yazı devam etti
    assert texts(s.feed([b(FULL)])[0]) == [FULL]  # cümle sonu var: iki okuma yeter


def test_line_without_end_punctuation_still_shown_after_extra_read():
    from src.translate.text import looks_complete
    s = TextStabilizer(looks_complete=lambda t: looks_complete(t, "ja"))
    line = "えっと、それは"
    outs = [texts(s.feed([b(line)])[0]) for _ in range(3)]
    assert outs == [[], [], [line]]  # bir okuma fazladan bekler, sonra gösterir
