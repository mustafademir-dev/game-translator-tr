"""Kullanıcı sözlüğü: {"田中": "Tanaka"}. Çeviriden önce kaynakta yer değiştirme yapar."""
from __future__ import annotations

import json
import re
from pathlib import Path


class Dictionary:
    def __init__(self, entries: dict[str, str] | None = None):
        self.entries: dict[str, str] = {}
        self._re: re.Pattern | None = None
        self.set_entries(entries or {})

    @classmethod
    def load(cls, path: Path) -> "Dictionary":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("dictionary.json bir nesne olmalı")
        return cls({str(k): str(v) for k, v in data.items() if k})

    def set_entries(self, entries: dict[str, str]) -> None:
        self.entries = dict(entries)
        keys = sorted(self.entries, key=len, reverse=True)  # uzun anahtar önce
        self._re = re.compile("|".join(map(re.escape, keys))) if keys else None

    def apply(self, text: str) -> str:
        if self._re is None:
            return text
        return self._re.sub(lambda m: self.entries[m.group(0)], text)

    def signature(self) -> tuple:
        return tuple(sorted(self.entries.items()))
