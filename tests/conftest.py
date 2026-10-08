import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.app_env import setup_offline_env  # noqa: E402

setup_offline_env()


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
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
