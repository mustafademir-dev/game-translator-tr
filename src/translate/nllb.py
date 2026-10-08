"""NLLB-200 backend'i: CTranslate2, int8, yalnızca CPU."""
from __future__ import annotations

import os
from pathlib import Path

SRC_LANG = "jpn_Jpan"
PIVOT_LANG = "eng_Latn"
TGT_LANG = "tur_Latn"


class ModelNotFoundError(RuntimeError):
    pass


class NllbBackend:
    def __init__(self, model_dir: Path, threads: int = 0, beam_size: int = 2, pivot: bool = False):
        import ctranslate2
        import sentencepiece as spm

        model_dir = Path(model_dir)
        sp_path = model_dir / "sentencepiece.bpe.model"
        if not (model_dir / "model.bin").exists() or not sp_path.exists():
            raise ModelNotFoundError(f"Model bulunamadı: {model_dir}")
        if threads <= 0:
            threads = max(1, (os.cpu_count() or 2) // 2)
        self.translator = ctranslate2.Translator(
            str(model_dir), device="cpu", compute_type="int8",
            inter_threads=1, intra_threads=threads,
        )
        # Dosyadan değil bayttan yükle: sentencepiece Windows'ta ASCII dışı yolları
        # (ör. "Masaüstü") açamıyor.
        self.sp = spm.SentencePieceProcessor(model_proto=sp_path.read_bytes())
        self.beam_size = beam_size
        self.pivot = pivot

    def _run(self, texts: list[str], src: str, tgt: str) -> list[str]:
        if not texts:
            return []
        sources = [[src, *self.sp.encode(t, out_type=str), "</s>"] for t in texts]
        results = self.translator.translate_batch(
            sources,
            target_prefix=[[tgt]] * len(sources),
            beam_size=self.beam_size,
            max_decoding_length=256,
            repetition_penalty=1.1,
        )
        return [self.sp.decode(r.hypotheses[0][1:]).strip() for r in results]

    def translate_batch(self, texts: list[str]) -> list[str]:
        if self.pivot:
            return self._run(self._run(texts, SRC_LANG, PIVOT_LANG), PIVOT_LANG, TGT_LANG)
        return self._run(texts, SRC_LANG, TGT_LANG)

    def translate(self, text: str, context: list[str] = []) -> str:
        return self.translate_batch([text])[0]
