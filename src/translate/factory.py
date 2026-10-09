"""Dile göre en iyi çeviri zincirini kurar (oyun modu ve resim modu ortak kullanır).

ja: Sugoi (ja→en) + opus-mt (en→tr)   en: opus-mt   ko: NLLB.   Eksik model -> NLLB.
Yalnızca gereken modeller yüklenir.
"""
from __future__ import annotations

from ..config import Config
from .service import TranslationService

MSG_MODEL = "Çeviri modeli bulunamadı. Önce 'py -3.11 setup.py' çalıştırın."
MSG_SUGOI = ("Sugoi (Japonca) modeli bulunamadı; Japonca için NLLB kullanılıyor.\n"
             "Kurmak için: py -3.11 setup.py --sugoi")


class NoModelError(RuntimeError):
    pass


def build_service(cfg: Config, lang: str, warn=lambda msg: None) -> TranslationService:
    """`warn(msg)`: model eksikse kullanıcıya gösterilecek uyarı. Hiç model yoksa NoModelError."""
    from .nllb import ModelNotFoundError, NllbBackend
    from .opus import OpusEnTrBackend, opus_available
    from .sugoi import SugoiBackend, SugoiChainBackend, sugoi_available

    threads, beam = cfg["threads"], cfg["beam_size"]
    use_sugoi = lang == "ja" and cfg["ja_model"] == "sugoi"
    if use_sugoi and not sugoi_available(cfg.sugoi_path()):
        warn(MSG_SUGOI)
        use_sugoi = False
    opus = None
    if (use_sugoi or lang == "en") and cfg["en_tr_model"] == "opus" and opus_available(cfg.opus_path()):
        opus = OpusEnTrBackend(cfg.opus_path(), threads=threads, beam_size=beam)
    nllb = None
    if opus is None or not (use_sugoi or lang == "en"):
        try:
            nllb = NllbBackend(cfg.model_path(), threads=threads, beam_size=beam, pivot=cfg["pivot"])
        except ModelNotFoundError as e:
            raise NoModelError(MSG_MODEL) from e
    if use_sugoi:
        sugoi = SugoiBackend(cfg.sugoi_path(), threads=threads, beam_size=beam,
                             compute_type=cfg["sugoi_compute"])
        backend = SugoiChainBackend(sugoi, opus or nllb)
    elif lang == "en" and opus is not None:
        backend = opus
    else:
        backend = nllb
    service = TranslationService(backend)
    service.set_language(lang)
    return service
