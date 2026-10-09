"""Metin düzeyinde stabilizasyon: yarım metni çevirme, OCR gürültüsüyle titreme.

Piksel düzeyindeki değişim tespiti (capture/change.py) yazının ne zaman bittiğini her zaman
bilemez: yazma efekti duraksayabilir, yazının arkasında karakter/arka plan hareket edebilir.
Bu yüzden OCR blokları konumlarına göre izlenir:

- Yeni metin, art arda iki okumada **benzer** (≥ %80) ve **uzamıyorsa** tamamlanmış sayılır.
  Yazı harf harf akarken metin her okumada uzadığı için yarım metin çevrilmez.
- Gösterilen metin "yapışkandır": aynı yerde benzer metin okundukça (tek tük harf farkı,
  hareketli arka plan gürültüsü) değişmez ve yeniden çevrilmez.
- Bir okumada kaçırılan blok hemen silinmez; art arda `max_misses` okumada yoksa silinir.
- Metin aynı yerde tamamen değişirse eskisi, yeni metin onaylanınca onunla değişir (tek bozuk
  okuma çeviriyi düşürmez). Oyunda tıklama / Enter / Boşluk ise çeviriyi hemen siler (app.py).
- Arka plandan çıkan rastgele "yazılar" her okumada başka olduğu için hiç onaylanmaz.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .base import TextBlock

SAME = 0.8      # bu benzerlikte iki okuma "aynı metin" sayılır
KEEP = 0.6      # gösterilen metin bu benzerlikte okunmaya devam ettikçe yerinde kalır
GROWTH = 2      # metin en az bu kadar karakter uzadıysa yazı hâlâ akıyor demektir


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _overlaps(a: TextBlock, b: TextBlock) -> bool:
    ix = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    iy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return ix > 0 and iy > 0


def completes(partial: str, full: str) -> bool:
    """`full`, yazı akarken okunan `partial` metnin tamamlanmış hali mi? (OCR gürültüsüne dayanıklı
    önek eşleşmesi: tamamı uzun olmalı ve başı yarım metne en az %80 benzemeli.)"""
    if len(full) - len(partial) < GROWTH or not partial:  # gerçekten uzamış olmalı
        return False
    return similarity(partial, full[:len(partial)]) >= SAME


def _settled(old: str, new: str) -> bool:
    return len(new) - len(old) < GROWTH and similarity(old, new) >= SAME


@dataclass
class _Track:
    block: TextBlock                 # son okunan blok (konum için)
    shown: str | None = None         # ekranda çevirisi gösterilen metin
    shown_block: TextBlock | None = None  # gösterilen metnin onaylandığı andaki konumu (titremesin)
    candidate: str | None = None     # onay bekleyen metin (son okuma)
    rounds: int = 0                  # kaç okumadır onay bekleniyor
    settles: int = 0                 # cümle sonu işareti olmadan kaç kez "aynı" okundu
    misses: int = 0                  # art arda kaç okumada görülmedi
    _seen: bool = field(default=False, repr=False)


class TextStabilizer:
    def __init__(self, max_rounds: int = 4, max_misses: int = 3, looks_complete=None):
        # Cümle sonu işaretiyle (。！？…) bitmeyen metin, yazma efektinin virgülde duraksamasıyla
        # yarım kalmış olabilir: böyle metin bir doğrulama okuması daha bekler.
        self.looks_complete = looks_complete or (lambda text: True)
        # Metin uzamadığı halde iki okuma hiç %80 benzer çıkmıyorsa (yoğun gürültü) en çok bu
        # kadar okuma beklenir; sonra son okuma, bir öncekine en az KEEP benzerse kabul edilir.
        self.max_rounds = max_rounds
        self.max_misses = max_misses
        self._tracks: list[_Track] = []

    def reset(self) -> None:
        self._tracks = []

    def _show(self, tr: _Track, b: TextBlock) -> None:
        tr.shown, tr.shown_block, tr.candidate, tr.rounds, tr.settles = b.text, b, None, 0, 0

    def _confirm(self, tr: _Track, b: TextBlock) -> None:
        """Aday iki okumada aynı çıktı. Cümle sonuyla bitiyorsa göster; bitmiyorsa bir kez daha bekle."""
        if self.looks_complete(b.text) or tr.settles >= 1:
            self._show(tr, b)
        else:
            tr.settles += 1
            tr.candidate, tr.rounds = b.text, tr.rounds + 1

    def _wait(self, tr: _Track, text: str) -> None:
        tr.candidate, tr.rounds, tr.settles = text, tr.rounds + 1, 0

    def _update(self, tr: _Track, b: TextBlock) -> None:
        text = b.text
        if tr.shown is not None:
            if len(text) - len(tr.shown) >= GROWTH and similarity(tr.shown, text) >= KEEP:
                # Gösterilen metin büyüyor (yarım kabul edilmişti): eskisi kalsın, uzunu onaylansın.
                if tr.candidate is not None and _settled(tr.candidate, text):
                    self._confirm(tr, b)
                else:
                    self._wait(tr, text)
                return
            if similarity(tr.shown, text) >= KEEP:
                tr.candidate, tr.rounds = None, 0  # aynı metin (gürültüyle): yerinde kalsın
                return
            # Çok farklı okuma: ya yeni replik ya da (kısa metinde) hareketli arka planın bozduğu
            # bir okuma. Eski çeviri, yeni metin iki okumada doğrulanana kadar yerinde kalır;
            # tek bir bozuk okuma çeviriyi düşürmez. (Tıklama zaten hemen siler.)
            if tr.candidate is not None and _settled(tr.candidate, text):
                self._confirm(tr, b)
            else:
                self._wait(tr, text)
            return
        if tr.candidate is not None and _settled(tr.candidate, text):
            self._confirm(tr, b)
        elif (tr.candidate is not None and tr.rounds >= self.max_rounds
              and len(text) - len(tr.candidate) < GROWTH and similarity(tr.candidate, text) >= KEEP):
            self._show(tr, b)  # gürültülü ama uzamıyor: kabul et
        else:
            self._wait(tr, text)

    def show_now(self, blocks: list[TextBlock]) -> list[TextBlock]:
        """Doğrulama beklemeden göster (ör. oyunda tıklayınca yazının tamamı geldi)."""
        for b in blocks:
            tr = next((t for t in self._tracks if _overlaps(t.block, b)), None)
            if tr is None:
                tr = _Track(b)
                self._tracks.append(tr)
            tr.block, tr.misses = b, 0
            self._show(tr, b)
        return [t.shown_block for t in self._tracks if t.shown is not None]

    def has_shown(self) -> bool:
        return any(t.shown is not None for t in self._tracks)

    def candidates(self) -> list[str]:
        """Onay bekleyen metinler (bir sonraki okumada doğrulanabilir)."""
        return [t.candidate for t in self._tracks if t.candidate is not None]

    def feed(self, blocks: list[TextBlock]) -> tuple[list[TextBlock], bool]:
        """Döner: (çevirisi gösterilecek bloklar, yakında yeniden okunmalı mı).
        Dönen bloklar onaylandıkları andaki haliyle (metin ve konum) döner; gürültüyle oynamaz."""
        for tr in self._tracks:
            tr._seen = False
        for b in blocks:
            tr = next((t for t in self._tracks if not t._seen and _overlaps(t.block, b)), None)
            if tr is None:
                tr = _Track(b)
                self._tracks.append(tr)
            tr._seen, tr.misses, tr.block = True, 0, b
            self._update(tr, b)
        for tr in self._tracks:
            if not tr._seen:
                tr.misses += 1
        self._tracks = [t for t in self._tracks if t.misses < self.max_misses
                        and (t.shown is not None or t._seen)]
        shown = [t.shown_block for t in self._tracks if t.shown is not None]
        waiting = any(t.candidate is not None for t in self._tracks)
        # Kaçırılan ama hâlâ gösterilen blok varsa da kısa süre sonra yeniden oku.
        missed = any(t.misses and t.shown is not None for t in self._tracks)
        return shown, waiting or missed
