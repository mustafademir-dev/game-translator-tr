import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.app_env import setup_offline_env  # noqa: E402

setup_offline_env()

# Uygulamadaki sırayı koru: CTranslate2, Paddle'dan önce yüklenmeli. Paddle'ın DLL'leri
# önce yüklenirse ctranslate2 importu WinError 127 ile düşüyor.
import ctranslate2  # noqa: E402,F401


@pytest.fixture(scope="session")
def qapp():
    # Ortam değişkeni değil argüman: alt süreçlere (sahte oyun, uygulama) miras kalmasın.
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["tests", "-platform", "offscreen"])
    return app


@pytest.fixture(scope="session")
def font_family(qapp):
    from PyQt6.QtGui import QFontDatabase
    from src.config import FONT_PATH
    if FONT_PATH.exists():
        fid = QFontDatabase.addApplicationFont(str(FONT_PATH))
        fams = QFontDatabase.applicationFontFamilies(fid)
        if fams:
            return fams[0]
    return qapp.font().family()
