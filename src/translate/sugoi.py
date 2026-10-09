"""Japonca için daha iyi çeviri zinciri: Sugoi (ja→en) + NLLB (en→tr).

NLLB'nin Japoncası zayıf, İngilizce→Türkçesi kabul edilebilir. Sugoi, Japonca oyun/görsel roman
metni için yaygın kullanılan bir Japonca→İngilizce modelidir (JParaCrawl tabanlı, NTT lisansı:
yalnızca araştırma amaçlı, ticari kullanım yok). Tamamen yerelde, CTranslate2 ile CPU'da çalışır;
ağ erişimi ve kayıt yoktur.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .nllb import NllbBackend

PIVOT = "eng_Latn"
TARGET = "tur_Latn"


# NLLB'nin sözlüğünde olmayan işaretler "⁇" olarak çıkıyor; İngilizce adımda sadeleştir.
_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "♪": " "})


def _normalize_english(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTES)).strip()


def decode_limit(sources: list[list[str]]) -> int:
    """Çıktı için en fazla token: en uzun girdinin ~2 katı (+16), en çok 200."""
    return min(200, 2 * max((len(s) for s in sources), default=0) + 16)


class SugoiNotFoundError(RuntimeError):
    pass


def sugoi_available(model_dir: Path) -> bool:
    model_dir = Path(model_dir)
    return ((model_dir / "model.bin").exists()
            and (model_dir / "spm" / "spm.ja.nopretok.model").exists()
            and (model_dir / "spm" / "spm.en.nopretok.model").exists())


class SugoiBackend:
    """Yalnızca Japonca → İngilizce."""

    def __init__(self, model_dir: Path, threads: int = 0, beam_size: int = 2, compute_type: str = "int16"):
        import ctranslate2
        import sentencepiece as spm

        model_dir = Path(model_dir)
        if not sugoi_available(model_dir):
            raise SugoiNotFoundError(f"Sugoi modeli bulunamadı: {model_dir}")
        if threads <= 0:
            threads = max(1, (os.cpu_count() or 2) // 2)
        # int8 sıkıştırma bu modelde anlamı bozuyor (soruları "bilmiyorum" diye çeviriyor, isim
        # uyduruyor). int16 float32 kadar doğru ve ~2.4 kat hızlı (cümle başına ~120 ms).
        self.translator = ctranslate2.Translator(
            str(model_dir), device="cpu", compute_type=compute_type, inter_threads=1, intra_threads=threads)
        # Bayttan yükle: sentencepiece ASCII dışı yolları (ör. "Masaüstü") açamıyor.
        self.sp_ja = spm.SentencePieceProcessor(model_proto=(model_dir / "spm" / "spm.ja.nopretok.model").read_bytes())
        self.sp_en = spm.SentencePieceProcessor(model_proto=(model_dir / "spm" / "spm.en.nopretok.model").read_bytes())
        self.beam_size = beam_size

    def translate_batch(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        src = [self.sp_ja.encode(t, out_type=str) for t in texts]
        # Çıktı uzunluğu girdiyle sınırlı: OCR'ın okuduğu anlamsız bir metin modelin saniyelerce
        # tekrar eden çıktı üretmesine yol açıyordu (kullanıcıda 23 s takılma).
        results = self.translator.translate_batch(
            src, beam_size=self.beam_size, max_decoding_length=decode_limit(src),
            repetition_penalty=1.1, no_repeat_ngram_size=4)
        return [_normalize_english(self.sp_en.decode(r.hypotheses[0]).replace("<unk>", "")) for r in results]


class SugoiChainBackend:
    """Japonca → (Sugoi) → İngilizce → (opus-mt ya da NLLB) → Türkçe.
    TranslationBackend arayüzünü uygular."""

    def __init__(self, sugoi: SugoiBackend, en_tr):
        """`en_tr`: OpusEnTrBackend (hızlı) ya da NllbBackend."""
        self.sugoi = sugoi
        self.en_tr = en_tr
        self.src_lang = "jpn_Jpan"  # TranslationService ayarlar; zincir yalnızca Japonca içindir
        self.pivot = False          # zincir zaten İngilizce üzerinden; pivot ayarı etkisiz

    def translate_batch(self, texts: list[str]) -> list[str]:
        english = self.sugoi.translate_batch(texts)
        if isinstance(self.en_tr, NllbBackend) or hasattr(self.en_tr, "_run"):
            return self.en_tr._run(english, PIVOT, TARGET)
        return self.en_tr.translate_batch(english)

    def translate(self, text: str, context: list[str] = []) -> str:
        return self.translate_batch([text])[0]
