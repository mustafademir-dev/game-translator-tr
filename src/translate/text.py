"""Metin yardımcıları: kaynak dil tanımları, dil tespiti ve cümle bölme.

Desteklenen kaynak diller: Japonca (ja), Korece (ko), İngilizce (en). Hedef her zaman Türkçe.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceLang:
    code: str        # profil/ayar kodu
    name: str        # arayüzde görünen ad
    nllb: str        # NLLB dil kodu
    ocr_tag: str     # Windows OCR dil etiketi
    ocr_capability: str  # Windows OCR dil paketi (Add-WindowsCapability adı)
    paddle: str      # PaddleOCR dil adı
    joins_without_space: bool  # satırlar/kelimeler boşluksuz birleşir mi (Japonca)
    vertical: bool   # dikey yazı olabilir mi


LANGS: dict[str, SourceLang] = {
    "ja": SourceLang("ja", "Japonca", "jpn_Jpan", "ja", "Language.OCR~~~ja-JP~0.0.1.0", "japan", True, True),
    "ko": SourceLang("ko", "Korece", "kor_Hang", "ko", "Language.OCR~~~ko-KR~0.0.1.0", "korean", False, False),
    "en": SourceLang("en", "İngilizce", "eng_Latn", "en-US", "Language.OCR~~~en-US~0.0.1.0", "en", False, False),
}
DEFAULT_LANG = "ja"

# Hiragana, katakana, CJK ideogramları, yarım genişlikli katakana.
_JP_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿ｦ-ﾟ]")
# Hangul heceleri ve harfleri.
_KO_RE = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")
# İngilizce: en az iki ardışık Latin harfi (tek harf ve yalnızca sayı içeren bloklar atılır).
_EN_RE = re.compile(r"[A-Za-z]{2,}")
_LANG_RE = {"ja": _JP_RE, "ko": _KO_RE, "en": _EN_RE}

# Japonca cümle: sonlandırıcıya kadar her şey, ardından ardışık sonlandırıcılar ve kapanış ayraçları.
_JA_SENTENCE_RE = re.compile(r"[^。！？]+(?:[。！？]+[」』）)\]]*)?|[。！？]+[」』）)\]]*")
# Korece / İngilizce: . ! ? (ve …) sonrası boşlukta böl; "3.5" gibi sayılar bölünmez.
_SPACE_SENTENCE_RE = re.compile(r"\S.*?(?:[.!?…]+[\"')\]]*(?=\s|$)|$)", re.S)


# Cümle sonu: metin bununla bitiyorsa büyük ihtimalle tamamlanmıştır (önden çeviri için ipucu).
_COMPLETE_RE = {
    "ja": re.compile(r"[。！？!?…」』）)]\s*$"),
    "ko": re.compile(r"[.!?…\"')\]]\s*$"),
    "en": re.compile(r"[.!?…\"')\]]\s*$"),
}


def looks_complete(text: str, lang: str = DEFAULT_LANG) -> bool:
    return bool(_COMPLETE_RE[lang].search(text))


def contains_japanese(text: str) -> bool:
    return bool(_JP_RE.search(text))


def contains_language(text: str, lang: str) -> bool:
    return bool(_LANG_RE[lang].search(text))


def split_sentences(text: str, lang: str = DEFAULT_LANG) -> list[str]:
    """Metni cümle sonlarından böler; işaret cümlede kalır, boş parçalar atılır.
    Japonca: 。！？  Korece/İngilizce: . ! ? … ardından boşluk."""
    if lang == "ja":
        parts = [m.group(0).strip() for m in _JA_SENTENCE_RE.finditer(text)]
    else:
        parts = [m.group(0).strip() for m in _SPACE_SENTENCE_RE.finditer(text)]
    return [p for p in parts if p]
