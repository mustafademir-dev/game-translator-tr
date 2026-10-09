"""Hızlı İngilizce → Türkçe: Helsinki-NLP opus-mt-tc-big-en-tr (MarianMT, CC-BY 4.0).

NLLB-1.3B'nin İngilizce→Türkçe adımı cümle başına ~470 ms sürüyordu ve Japonca zincirinin
(Sugoi ja→en → en→tr) darboğazıydı. Bu model çok daha küçük; CTranslate2 int8 ile CPU'da çalışır.
Tamamen yereldir; ağ erişimi ve kayıt yoktur.
"""
from __future__ import annotations

import os
from pathlib import Path


def opus_available(model_dir: Path) -> bool:
    model_dir = Path(model_dir)
    return all((model_dir / f).exists() for f in ("model.bin", "source.spm", "target.spm"))


class OpusEnTrBackend:
    """İngilizce → Türkçe. TranslationBackend arayüzünü de uygular (İngilizce oyunlar için)."""

    def __init__(self, model_dir: Path, threads: int = 0, beam_size: int = 2):
        import ctranslate2
        import sentencepiece as spm

        model_dir = Path(model_dir)
        if not opus_available(model_dir):
            raise FileNotFoundError(f"opus-mt en-tr modeli bulunamadı: {model_dir}")
        if threads <= 0:
            threads = max(1, (os.cpu_count() or 2) // 2)
        self.translator = ctranslate2.Translator(
            str(model_dir), device="cpu", compute_type="int8", inter_threads=1, intra_threads=threads)
        # Bayttan yükle: sentencepiece ASCII dışı yolları (ör. "Masaüstü") açamıyor.
        self.sp_src = spm.SentencePieceProcessor(model_proto=(model_dir / "source.spm").read_bytes())
        self.sp_tgt = spm.SentencePieceProcessor(model_proto=(model_dir / "target.spm").read_bytes())
        self.beam_size = beam_size
        self.src_lang = "eng_Latn"  # TranslationService ayarlar; bu model yalnızca İngilizce alır
        self.pivot = False

    def translate_batch(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        from .sugoi import decode_limit
        src = [self.sp_src.encode(t, out_type=str) + ["</s>"] for t in texts]
        results = self.translator.translate_batch(
            src, beam_size=self.beam_size, max_decoding_length=decode_limit(src),
            repetition_penalty=1.1, no_repeat_ngram_size=4)
        return [self.sp_tgt.decode([p for p in r.hypotheses[0] if p != "</s>"]).strip() for r in results]

    def translate(self, text: str, context: list[str] = []) -> str:
        return self.translate_batch([text])[0]
