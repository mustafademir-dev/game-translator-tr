"""Bellek içi çeviri önbelleği (diske yazılmaz)."""
from __future__ import annotations

import threading
from collections import OrderedDict


class TranslationCache:
    def __init__(self, max_items: int = 2000):
        self.max_items = max_items
        self._data: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.max_items:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)
