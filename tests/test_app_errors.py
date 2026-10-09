"""Hata bildirimleri: sessizce geçilmez, metin içeriği mesaja girmez."""
from src import app as app_mod
from src.config import Config


def test_model_missing_emits_notification(qapp, tmp_path):
    cfg = Config(tmp_path / "settings.json")
    cfg.data["model_dir"] = str(tmp_path / "yok")
    p = app_mod.Pipeline(cfg, "ko")  # Korece NLLB'ye muhtaç (Japonca/İngilizce artık NLLB'siz çalışabilir)
    got = []
    p.error.connect(got.append)
    assert p._load_backend() is False
    assert got == [app_mod.MSG_MODEL]


def test_ocr_missing_message_has_install_command():
    assert 'Add-WindowsCapability -Online -Name "Language.OCR~~~ja-JP~0.0.1.0"' in app_mod.MSG_OCR


def test_ocr_unavailable_emits_notification(qapp, tmp_path, monkeypatch):
    from src.ocr import OcrUnavailableError

    def boom(name, lang="ja"):
        raise OcrUnavailableError("yok")

    monkeypatch.setattr(app_mod, "create_engine", boom)
    p = app_mod.Pipeline(Config(tmp_path / "settings.json"))
    got = []
    p.error.connect(got.append)
    assert p._engine() is None
    assert got == [app_mod.MSG_OCR]
    assert p._engine() is None and len(got) == 1  # tekrar tekrar bildirmez
