"""Uygulama başlarken ilk iş çağrılır: offline ve telemetri kapatma ortam değişkenleri."""
from __future__ import annotations

import os

OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HF_DATASETS_OFFLINE": "1",
    "DO_NOT_TRACK": "1",
    # PaddleOCR / PaddleX: model kaynak kontrolü ve indirme yok.
    "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True",
    "FLAGS_call_stack_level": "0",
}


def setup_offline_env() -> None:
    for k, v in OFFLINE_ENV.items():
        os.environ[k] = v
