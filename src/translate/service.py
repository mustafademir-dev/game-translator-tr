"""Sözlük + cümle bölme + önbellek + backend'i birleştiren katman."""
from __future__ import annotations

import threading

from .backend import TranslationBackend
from .cache import TranslationCache
from .dictionary import Dictionary
from .text import split_sentences


class TranslationService:
    def __init__(self, backend: TranslationBackend, dictionary: Dictionary | None = None,
                 cache_size: int = 2000):
        self.backend = backend
        self.dictionary = dictionary or Dictionary()
        self.cache = TranslationCache(cache_size)
        self._lock = threading.Lock()  # backend aynı anda tek çağrı alır

    def set_dictionary(self, dictionary: Dictionary) -> None:
        if dictionary.signature() != self.dictionary.signature():
            self.dictionary = dictionary
            self.cache.clear()

    def set_pivot(self, pivot: bool) -> None:
        if getattr(self.backend, "pivot", None) != pivot:
            self.backend.pivot = pivot
            self.cache.clear()

    def translate(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        cached = self.cache.get(text)
        if cached is not None:
            return cached
        pieces = split_sentences(self.dictionary.apply(text))
        with self._lock:
            if hasattr(self.backend, "translate_batch"):
                out = self.backend.translate_batch(pieces)
            else:
                out = [self.backend.translate(p) for p in pieces]
        result = " ".join(o for o in out if o)
        self.cache.put(text, result)
        return result
