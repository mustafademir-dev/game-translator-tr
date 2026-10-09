from src.translate import Dictionary, TranslationCache, TranslationService, contains_japanese, split_sentences


class FakeBackend:
    def __init__(self):
        self.calls: list[str] = []
        self.pivot = False

    def translate(self, text, context=[]):
        self.calls.append(text)
        return f"<{text}>"


# --- cache ---

def test_cache_lru_limit():
    c = TranslationCache(max_items=3)
    for i in range(5):
        c.put(str(i), f"v{i}")
    assert len(c) == 3
    assert c.get("0") is None and c.get("1") is None
    assert c.get("4") == "v4"


def test_cache_recent_use_survives():
    c = TranslationCache(max_items=2)
    c.put("a", "1")
    c.put("b", "2")
    c.get("a")
    c.put("c", "3")
    assert c.get("a") == "1" and c.get("b") is None


def test_service_uses_cache():
    be = FakeBackend()
    s = TranslationService(be)
    s.translate("こんにちは。")
    s.translate("こんにちは。")
    assert len(be.calls) == 1


def test_service_default_cache_size():
    assert TranslationService(FakeBackend()).cache.max_items == 2000


def test_cache_cleared_on_dictionary_change():
    be = FakeBackend()
    s = TranslationService(be)
    s.translate("田中です。")
    s.set_dictionary(Dictionary({"田中": "Tanaka"}))
    assert s.translate("田中です。") == "<Tanakaです。>"
    assert len(be.calls) == 2


def test_cache_kept_on_same_dictionary():
    be = FakeBackend()
    s = TranslationService(be, Dictionary({"田中": "Tanaka"}))
    s.translate("田中です。")
    s.set_dictionary(Dictionary({"田中": "Tanaka"}))
    s.translate("田中です。")
    assert len(be.calls) == 1


def test_cache_cleared_on_pivot_change():
    be = FakeBackend()
    s = TranslationService(be)
    s.translate("はい。")
    s.set_pivot(True)
    s.translate("はい。")
    assert len(be.calls) == 2 and be.pivot is True


# --- sözlük ---

def test_dictionary_longest_key_first():
    d = Dictionary({"田中": "Tanaka", "田中太郎": "Tanaka Tarou"})
    assert d.apply("田中太郎と田中") == "Tanaka TarouとTanaka"


def test_dictionary_no_entries():
    assert Dictionary().apply("こんにちは") == "こんにちは"


def test_dictionary_load(tmp_path):
    p = tmp_path / "dictionary.json"
    p.write_text('{"桜井": "Sakurai"}', encoding="utf-8")
    assert Dictionary.load(p).apply("桜井さん") == "Sakuraiさん"
    assert Dictionary.load(tmp_path / "yok.json").entries == {}


def test_dictionary_output_not_corrected():
    class Dropper(FakeBackend):
        def translate(self, text, context=[]):
            return "isim kayboldu"
    s = TranslationService(Dropper(), Dictionary({"田中": "Tanaka"}))
    assert s.translate("田中です。") == "isim kayboldu"


# --- cümle bölme ---

def test_split_basic():
    assert split_sentences("はい。そうです！本当？") == ["はい。", "そうです！", "本当？"]


def test_split_keeps_multiple_marks_and_quotes():
    assert split_sentences("「えっ！？」まさか。") == ["「えっ！？」", "まさか。"]


def test_split_no_terminator():
    assert split_sentences("ちょっと待って") == ["ちょっと待って"]


def test_split_trailing_and_whitespace():
    assert split_sentences(" はい。 \n いいえ") == ["はい。", "いいえ"]


def test_service_splits_long_text():
    be = FakeBackend()
    TranslationService(be).translate("一。二！三？")
    assert be.calls == ["一。", "二！", "三？"]


def test_contains_japanese():
    assert contains_japanese("abcあ")
    assert contains_japanese("漢字")
    assert contains_japanese("ｶﾀｶﾅ")
    assert not contains_japanese("hello 123 !?")


# --- Korece / İngilizce ---

def test_contains_language():
    from src.translate import contains_language
    assert contains_language("안녕하세요", "ko") and not contains_language("こんにちは", "ko")
    assert contains_language("Hello there", "en") and contains_language("HP 100", "en")
    assert not contains_language("100 / 3 x", "en")
    assert contains_language("こんにちは", "ja") and not contains_language("Hello", "ja")


def test_split_english_keeps_quotes_and_decimals():
    assert split_sentences('He said "Hi." Then he left! It costs 3.5 dollars. Wait', "en") == [
        'He said "Hi."', "Then he left!", "It costs 3.5 dollars.", "Wait"]


def test_split_korean():
    assert split_sentences("안녕하세요. 오늘 학교에 안 와요? 정말", "ko") == [
        "안녕하세요.", "오늘 학교에 안 와요?", "정말"]


def test_service_language_switch():
    be = FakeBackend()
    s = TranslationService(be)
    assert be.src_lang == "jpn_Jpan"
    s.translate("Hi. Bye.")  # Japonca kuralı: . ile bölünmez
    s.set_language("en")
    assert be.src_lang == "eng_Latn"
    s.translate("Hi. Bye.")
    assert be.calls == ["Hi. Bye.", "Hi.", "Bye."]  # dil değişince önbellek de temizlendi
    s.set_language("ko")
    assert be.src_lang == "kor_Hang"


def test_subtitle_dash_removed_but_negative_numbers_kept():
    from src.translate.nllb import _clean
    assert _clean("- Günaydın.") == "Günaydın."
    assert _clean("  -  Evet.") == "Evet."
    assert _clean("-5 derece soğuk.") == "-5 derece soğuk."
    assert _clean("Bekle - geliyorum.") == "Bekle - geliyorum."


def test_sugoi_chain_goes_through_english():
    """Japonca: Sugoi (ja→en) çıktısı NLLB'ye İngilizce kaynak olarak girer."""
    from src.translate.sugoi import SugoiChainBackend

    class FakeSugoi:
        def translate_batch(self, texts):
            return [f"EN({t})" for t in texts]

    class FakeNllb:
        def __init__(self):
            self.calls = []

        def _run(self, texts, src, tgt):
            self.calls.append((src, tgt))
            return [f"TR({t})" for t in texts]

    nllb = FakeNllb()
    s = TranslationService(SugoiChainBackend(FakeSugoi(), nllb))
    s.set_language("ja")
    assert s.translate("はい。いいえ。") == "TR(EN(はい。)) TR(EN(いいえ。))"
    assert nllb.calls == [("eng_Latn", "tur_Latn")]


def test_looks_complete():
    from src.translate.text import looks_complete
    assert looks_complete("はい、そうです。", "ja") and looks_complete("「えっ！？」", "ja")
    assert not looks_complete("はい、そう", "ja") and not looks_complete("いいえ、", "ja")
    assert looks_complete("Where are you going?", "en") and not looks_complete("Wait, where", "en")
    assert looks_complete("정말?", "ko")
