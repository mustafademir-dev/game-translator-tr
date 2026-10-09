"""Manga / çizgi roman için OCR (yalnızca Japonca, resim modu).

Windows OCR yatay metin için yapılmış: mangadaki dikey yazıyı ve furigana'yı (kanjinin yanındaki
küçük okunuş) karıştırıyor, çeviri de anlamsızlaşıyordu. Bu motor iki adımlıdır:

1. Yazı bölgelerini bul: PaddleOCR'ın yalnızca tespit kısmı (resim 2 kat büyütülerek, hassas
   ayarla) + Windows OCR satır kutuları. Yakın kutular (aynı balondaki sütunlar ve furigana)
   tek bölgede birleştirilir.
2. Her bölgeyi kırpıp manga-ocr ile oku (kha-white/manga-ocr-base, Apache-2.0): manga
   balonları için eğitilmiş, dikey yazıyı doğru sırada okur, furigana'yı görmezden gelir.

Tamamen yerelde çalışır; ağ erişimi ve kayıt yoktur.
"""
from __future__ import annotations

import os
import re

import numpy as np

from ..config import ROOT
from ..translate.text import contains_japanese
from .base import OcrUnavailableError, TextBlock

MANGA_OCR_DIR = ROOT / "models" / "manga-ocr-base"


def manga_ocr_available() -> bool:
    return (MANGA_OCR_DIR / "pytorch_model.bin").exists() and (MANGA_OCR_DIR / "vocab.txt").exists()


def _to_fullwidth(text: str) -> str:
    # manga-ocr'ın kendi son işlemi: yarım genişlikli ASCII/rakam -> tam genişlik (jaconv.h2z gibi)
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in text)


def _postprocess(text: str) -> str:
    text = "".join(text.split())
    text = text.replace("…", "...")
    text = re.sub(r"[・.]{2,}", lambda m: (m.end() - m.start()) * ".", text)
    return _to_fullwidth(text)


def cluster_boxes(boxes: list[tuple[int, int, int, int]], margin_ratio: float = 0.35,
                  max_margin: int = 20) -> list[tuple[int, int, int, int]]:
    """Yakın kutuları (aynı balondaki sütunlar, furigana) tek bölgede birleştir.
    Her kutu yazı boyutunun (kısa kenarının) ~üçte biri kadar büyütülür, kesişenler aynı bölgeye
    girer (bağlı bileşenler). Pay yalnızca orijinal kutulardan hesaplanır; birleşen bölgeyi tekrar
    büyütmek zincirleme olarak paneller arası balonları yutuyordu."""
    n = len(boxes)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grown = []
    for x, y, w, h in boxes:
        m = min(max_margin, max(3, int(margin_ratio * min(w, h))))
        grown.append((x - m, y - m, x + w + m, y + h + m))
    for i in range(n):
        for j in range(i + 1, n):
            a, b = grown[i], grown[j]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for members in groups.values():
        x0 = min(boxes[i][0] for i in members)
        y0 = min(boxes[i][1] for i in members)
        x1 = max(boxes[i][0] + boxes[i][2] for i in members)
        y1 = max(boxes[i][1] + boxes[i][3] for i in members)
        out.append((x0, y0, x1 - x0, y1 - y0))
    return out


class MangaOcrEngine:
    def __init__(self, lang: str = "ja"):
        if lang != "ja":
            raise OcrUnavailableError("Manga OCR yalnızca Japonca")
        if not manga_ocr_available():
            raise OcrUnavailableError("manga-ocr modeli yok (setup.py --manga)")
        try:
            import torch
            from transformers import ViTImageProcessor, VisionEncoderDecoderModel
        except ImportError as e:
            raise OcrUnavailableError("manga-ocr için torch/transformers kurulu değil") from e
        torch.set_num_threads(max(1, (os.cpu_count() or 2) // 2))
        self._torch = torch
        path = str(MANGA_OCR_DIR)
        self.processor = ViTImageProcessor.from_pretrained(path, local_files_only=True)
        # Çıktıyı çözmek için yalnızca sözlük yeter (tokenizer'ın istediği fugashi/MeCab gereksiz).
        self.vocab = (MANGA_OCR_DIR / "vocab.txt").read_text(encoding="utf-8").splitlines()
        self.model = VisionEncoderDecoderModel.from_pretrained(path, local_files_only=True).eval()
        self._detector = self._make_paddle_detector()
        from .winocr import WindowsOcrEngine, ocr_language_available
        self._win = WindowsOcrEngine("ja") if ocr_language_available("ja") else None
        if self._detector is None and self._win is None:
            raise OcrUnavailableError("Yazı bölgesi bulmak için PaddleOCR ya da Windows OCR Japonca gerekli")

    @staticmethod
    def _make_paddle_detector():
        """PaddleOCR'ın yalnızca tespit kısmı; kurulu değilse None (yalnızca Windows OCR kutuları)."""
        from .paddle import paddle_model_dir
        rel = paddle_model_dir("ja")
        if not (ROOT / rel / "det" / "inference.pdmodel").exists():
            return None
        try:
            from paddleocr import PaddleOCR
        except ImportError:
            return None
        cwd = os.getcwd()
        os.chdir(ROOT)  # Paddle ASCII dışı mutlak yolları açamıyor
        try:
            return PaddleOCR(lang="japan", use_angle_cls=False, use_gpu=False, show_log=False,
                             det_model_dir=f"{rel}/det", rec_model_dir=f"{rel}/rec", cls_model_dir=f"{rel}/cls",
                             det_db_thresh=0.2, det_db_box_thresh=0.3, det_db_unclip_ratio=2.0,
                             det_limit_side_len=2400)
        finally:
            os.chdir(cwd)

    def _detect(self, bgra: np.ndarray) -> list[tuple[int, int, int, int]]:
        boxes = []
        if self._detector is not None:
            bgr = np.ascontiguousarray(bgra[:, :, :3])
            scale = 2 if max(bgr.shape[:2]) <= 1600 else 1  # küçük resimde küçük yazı için büyüt
            if scale > 1:
                bgr = bgr.repeat(scale, axis=0).repeat(scale, axis=1)
            for poly in (self._detector.ocr(bgr, rec=False, cls=False) or [[]])[0] or []:
                xs = [p[0] / scale for p in poly]
                ys = [p[1] / scale for p in poly]
                boxes.append((int(min(xs)), int(min(ys)), int(max(xs) - min(xs)) + 1, int(max(ys) - min(ys)) + 1))
        if self._win is not None:
            boxes += [(b.x, b.y, b.w, b.h) for b in self._win.recognize(bgra)]
        return [b for b in boxes if b[2] >= 4 and b[3] >= 4]

    def _read(self, bgra: np.ndarray, box: tuple[int, int, int, int]) -> str:
        from PIL import Image
        x, y, w, h = box
        pad = max(4, int(0.15 * min(w, h)))
        H, W = bgra.shape[:2]
        crop = bgra[max(0, y - pad):min(H, y + h + pad), max(0, x - pad):min(W, x + w + pad), [2, 1, 0]]
        img = Image.fromarray(np.ascontiguousarray(crop)).convert("L").convert("RGB")
        pixels = self.processor(img, return_tensors="pt").pixel_values
        with self._torch.inference_mode():
            ids = self.model.generate(pixels, max_length=120)[0]
        return _postprocess(self._decode(ids.tolist()))

    def _decode(self, ids: list[int]) -> str:
        out = []
        for i in ids:
            tok = self.vocab[i] if 0 <= i < len(self.vocab) else ""
            if tok.startswith("[") and tok.endswith("]"):  # [CLS] [SEP] [PAD] [UNK] ...
                continue
            out.append(tok[2:] if tok.startswith("##") else tok)
        return "".join(out)

    def recognize(self, image: np.ndarray) -> list[TextBlock]:
        if image.shape[2] == 3:
            image = np.dstack([image, np.full(image.shape[:2], 255, np.uint8)])
        out = []
        for box in cluster_boxes(self._detect(image)):
            x, y, w, h = box
            if w * h < 150:
                continue
            text = self._read(image, box)
            if contains_japanese(text):
                out.append(TextBlock(text, x, y, w, h, vertical=h > 1.2 * w))
        return out
