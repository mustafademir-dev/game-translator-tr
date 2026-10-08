"""Çeviri hızı ve kalitesi karşılaştırması: doğrudan (ja→tr) ve pivot (ja→en→tr).

Kullanım:
    venv\\Scripts\\python.exe tools\\benchmark.py [cumleler.txt]
Sonuçlar yalnızca ekrana basılır, diske yazılmaz.
"""
from __future__ import annotations

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
from src.translate.text import split_sentences  # noqa: E402


def p95(values: list[float]) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]


def timed(backend: NllbBackend, text: str) -> tuple[str, float]:
    t0 = time.perf_counter()
    out = " ".join(backend.translate_batch(split_sentences(text)))
    return out, time.perf_counter() - t0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("benchmark_sentences.txt")
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    cfg = Config()
    print(f"Model: {cfg.model_path()}")
    backend = NllbBackend(cfg.model_path(), threads=cfg["threads"], beam_size=cfg["beam_size"])
    backend.translate_batch(["ウォームアップ。"])  # ilk çağrı ölçüme girmesin

    direct, pivot, mid = [], [], []
    for i, line in enumerate(lines, 1):
        backend.pivot = False
        d_out, d_t = timed(backend, line)
        backend.pivot = True
        p_out, p_t = timed(backend, line)
        direct.append(d_t)
        pivot.append(p_t)
        if 20 <= len(line) <= 100:
            mid.append(d_t)
        print(f"\n[{i:02d}] ({len(line)} kr) {line}")
        print(f"  doğrudan {d_t*1000:6.0f} ms | {d_out}")
        print(f"  pivot    {p_t*1000:6.0f} ms | {p_out}")

    print("\n=== Özet ===")
    print(f"doğrudan: medyan {statistics.median(direct)*1000:.0f} ms, p95 {p95(direct)*1000:.0f} ms")
    print(f"pivot   : medyan {statistics.median(pivot)*1000:.0f} ms, p95 {p95(pivot)*1000:.0f} ms")
    if mid:
        med = statistics.median(mid)
        print(f"20-100 karakter (doğrudan, {len(mid)} cümle): medyan {med*1000:.0f} ms, "
              f"p95 {p95(mid)*1000:.0f} ms -> {'GEÇTİ' if med < 1.0 else 'KALDI'} (< 1000 ms)")


if __name__ == "__main__":
    main()
