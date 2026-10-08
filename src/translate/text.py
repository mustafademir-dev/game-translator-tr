"""Metin yardımcıları: Japonca tespiti ve cümle bölme."""
from __future__ import annotations

import re

# Hiragana, katakana, CJK ideogramları, yarım genişlikli katakana.
_JP_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿ｦ-ﾟ]")

# Cümle: sonlandırıcıya kadar her şey, ardından ardışık sonlandırıcılar ve kapanış ayraçları.
_SENTENCE_RE = re.compile(r"[^。！？]+(?:[。！？]+[」』）)\]]*)?|[。！？]+[」』）)\]]*")


def contains_japanese(text: str) -> bool:
    return bool(_JP_RE.search(text))


def split_sentences(text: str) -> list[str]:
    """Metni 。！？ işaretlerinden böler; işaret cümlede kalır, boş parçalar atılır."""
    parts = [m.group(0).strip() for m in _SENTENCE_RE.finditer(text)]
    return [p for p in parts if p]
