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
