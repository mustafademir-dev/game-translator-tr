"""Çeviri hızı ve kalitesi karşılaştırması: doğrudan (kaynak→tr) ve pivot (kaynak→en→tr).

Kullanım:
    venv\\Scripts\\python.exe tools\\benchmark.py [cumleler.txt] [--lang ja|ko|en]
Dil verilmezse Japonca; dosya verilmezse o dilin örnek dosyası kullanılır.
İngilizce kaynakta pivot adımı yoktur (doğrudan ile aynıdır).
Sonuçlar yalnızca ekrana basılır, diske yazılmaz.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.app_env import setup_offline_env  # noqa: E402

setup_offline_env()

from src.config import Config  # noqa: E402
from src.translate.nllb import NllbBackend  # noqa: E402
from src.translate.sugoi import SugoiBackend, SugoiChainBackend, sugoi_available  # noqa: E402
from src.translate.text import LANGS, split_sentences  # noqa: E402


def p95(values: list[float]) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]


def timed(backend, text: str, lang: str) -> tuple[str, float]:
    t0 = time.perf_counter()
    out = " ".join(backend.translate_batch(split_sentences(text, lang)))
    return out, time.perf_counter() - t0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="her satırda bir cümle")
    ap.add_argument("--lang", choices=sorted(LANGS), default="ja", help="kaynak dil")
    args = ap.parse_args()
    default = "benchmark_sentences.txt" if args.lang == "ja" else f"benchmark_sentences_{args.lang}.txt"
    path = Path(args.file) if args.file else Path(__file__).with_name(default)
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    cfg = Config()
    print(f"Model: {cfg.model_path()}")
    print(f"Kaynak dil: {LANGS[args.lang].name} -> Türkçe")
    backend = NllbBackend(cfg.model_path(), threads=cfg["threads"], beam_size=cfg["beam_size"])
    backend.src_lang = LANGS[args.lang].nllb
    backend.translate_batch([lines[0]])  # ilk çağrı ölçüme girmesin
    chain = None
    if args.lang == "ja" and sugoi_available(cfg.sugoi_path()):
        chain = SugoiChainBackend(SugoiBackend(cfg.sugoi_path(), threads=cfg["threads"],
                                               beam_size=cfg["beam_size"],
                                               compute_type=cfg["sugoi_compute"]), backend)
        chain.translate_batch([lines[0]])
        print("Sugoi zinciri (ja→en→tr) de ölçülüyor")

    direct, pivot, mid, sug, sug_mid = [], [], [], [], []
    for i, line in enumerate(lines, 1):
        backend.pivot = False
        d_out, d_t = timed(backend, line, args.lang)
        backend.pivot = True
        p_out, p_t = timed(backend, line, args.lang)
        direct.append(d_t)
        pivot.append(p_t)
        if 20 <= len(line) <= 100:
            mid.append(d_t)
        print(f"\n[{i:02d}] ({len(line)} kr) {line}")
        print(f"  doğrudan {d_t*1000:6.0f} ms | {d_out}")
        print(f"  pivot    {p_t*1000:6.0f} ms | {p_out}")
        if chain:
            backend.pivot = False
            s_out, s_t = timed(chain, line, args.lang)
            sug.append(s_t)
            if 20 <= len(line) <= 100:
                sug_mid.append(s_t)
            print(f"  sugoi    {s_t*1000:6.0f} ms | {s_out}")

    print("\n=== Özet ===")
    print(f"doğrudan: medyan {statistics.median(direct)*1000:.0f} ms, p95 {p95(direct)*1000:.0f} ms")
    print(f"pivot   : medyan {statistics.median(pivot)*1000:.0f} ms, p95 {p95(pivot)*1000:.0f} ms")
    if sug:
        print(f"sugoi   : medyan {statistics.median(sug)*1000:.0f} ms, p95 {p95(sug)*1000:.0f} ms")
    if sug_mid:
        print(f"20-100 karakter (sugoi, {len(sug_mid)} cümle): medyan {statistics.median(sug_mid)*1000:.0f} ms")
    if mid:
        med = statistics.median(mid)
        print(f"20-100 karakter (doğrudan, {len(mid)} cümle): medyan {med*1000:.0f} ms, "
              f"p95 {p95(mid)*1000:.0f} ms -> {'GEÇTİ' if med < 1.0 else 'KALDI'} (< 1000 ms)")


if __name__ == "__main__":
    main()
