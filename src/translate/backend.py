"""Çeviri backend arayüzü."""
from __future__ import annotations

from typing import Protocol


class TranslationBackend(Protocol):
    def translate(self, text: str, context: list[str] = []) -> str:
        """`context` şimdilik kullanılmaz; ileride LLM backend'i için arayüzde durur."""
        ...
