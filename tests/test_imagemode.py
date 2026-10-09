"""Resim modu: dosya listesi ve görüntü dönüşümü (ekran/fare kullanmaz)."""
import numpy as np
from PIL import Image

from src.imagemode import list_images, qimage_to_bgra


def make(p, color=(10, 20, 30)):
    Image.new("RGB", (8, 6), color).save(p)


def test_folder_natural_order_and_non_images_skipped(tmp_path):
    for n in ("10.png", "2.png", "1.jpg", "notlar.txt"):
        (make(tmp_path / n) if n.endswith(("png", "jpg")) else (tmp_path / n).write_text("x"))
    files, start = list_images([tmp_path])
    assert [f.name for f in files] == ["1.jpg", "2.png", "10.png"] and start == 0


def test_single_file_opens_its_folder_at_that_file(tmp_path):
    for n in ("a.png", "b.png", "c.png"):
        make(tmp_path / n)
    files, start = list_images([tmp_path / "b.png"])
    assert [f.name for f in files] == ["a.png", "b.png", "c.png"] and start == 1


def test_qimage_to_bgra(qapp, tmp_path):
    from PyQt6.QtGui import QImage
    make(tmp_path / "x.png", (200, 100, 50))
    arr = qimage_to_bgra(QImage(str(tmp_path / "x.png")))
    assert arr.shape == (6, 8, 4)
    assert tuple(arr[0, 0, :3]) == (50, 100, 200)  # BGR
