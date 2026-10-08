"""Kurulum betiği. Ağ erişimi olan tek yer burasıdır.

Kullanım (Python 3.11 ile):
    py -3.11 setup.py            # venv, bağımlılıklar, model, font
    py -3.11 setup.py --paddle   # ek olarak PaddleOCR (isteğe bağlı)
    py -3.11 setup.py --model 600M   # RAM ölçümünü yok say, modeli zorla
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / "venv"
MODELS = ROOT / "models"
ASSETS = ROOT / "assets"
SETTINGS = ROOT / "settings.json"

RUNTIME_PACKAGES = [
    "ctranslate2>=4.4,<5",
    "sentencepiece>=0.2",
    "PyQt6>=6.6",
    "mss>=9",
    "numpy>=1.26",
    "Pillow>=10",
    "winsdk>=1.0.0b10",
    "pytest>=8",
]
# Yalnızca model dönüşümü için gerekir; uygulama çalışırken import edilmez.
CONVERT_PACKAGES = [
    "huggingface_hub>=0.23",
    "transformers>=4.40,<5",
    "protobuf",
]
TORCH_INDEX = "https://download.pytorch.org/whl/cpu"
PADDLE_PACKAGES = ["paddlepaddle==2.6.2", "paddleocr==2.9.1", "setuptools"]

MODEL_IDS = {
    "1.3B": "facebook/nllb-200-distilled-1.3B",
    "600M": "facebook/nllb-200-distilled-600M",
}
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf"
FONT_LICENSE_URL = "https://github.com/google/fonts/raw/main/ofl/notosans/OFL.txt"

OCR_CAPABILITY_CMD = 'Add-WindowsCapability -Online -Name "Language.OCR~~~ja-JP~0.0.1.0"'


def log(msg: str) -> None:
    print(f"[setup] {msg}", flush=True)


def venv_python() -> Path:
    return VENV / "Scripts" / "python.exe"


def run(cmd: list[str]) -> None:
    log(" ".join(str(c) for c in cmd))
    subprocess.check_call([str(c) for c in cmd])


def total_ram_gb() -> float:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    return stat.ullTotalPhys / 1024**3


def choose_model(forced: str | None) -> str:
    if forced:
        return forced
    ram = total_ram_gb()
    # "12 GB" sınırı: 16 GB'lık makineler Windows'ta ~15.7 GB raporlar,
    # 12 GB'lık olanlar ~11.8 GB. Bu yüzden 11.5 eşik olarak kullanılır.
    choice = "1.3B" if ram >= 11.5 else "600M"
    log(f"Sistem RAM'i: {ram:.1f} GB -> NLLB {choice}")
    return choice


def ensure_venv() -> None:
    if sys.version_info[:2] != (3, 11):
        log(f"UYARI: Python 3.11 bekleniyor, bu {sys.version.split()[0]}. "
            "'py -3.11 setup.py' ile çalıştırın.")
    if not venv_python().exists():
        run([sys.executable, "-m", "venv", VENV])
    run([venv_python(), "-m", "pip", "install", "-q", "--upgrade", "pip"])
    run([venv_python(), "-m", "pip", "install", "-q", *RUNTIME_PACKAGES])


def model_dir(choice: str) -> Path:
    return MODELS / f"nllb-{choice}-ct2-int8"


def install_model(choice: str) -> None:
    out = model_dir(choice)
    if (out / "model.bin").exists() and (out / "sentencepiece.bpe.model").exists():
        log(f"Model zaten var: {out}")
        return
    run([venv_python(), "-m", "pip", "install", "-q", "torch", "--index-url", TORCH_INDEX])
    run([venv_python(), "-m", "pip", "install", "-q", *CONVERT_PACKAGES])
    hf_dir = MODELS / "hf" / MODEL_IDS[choice].split("/")[1]
    download = (
        "from huggingface_hub import snapshot_download;"
        f"snapshot_download({MODEL_IDS[choice]!r}, local_dir={str(hf_dir)!r},"
        "allow_patterns=['*.json','*.model','pytorch_model.bin'])"
    )
    env = dict(os.environ, HF_HUB_DISABLE_TELEMETRY="1")
    log(f"Model indiriliyor: {MODEL_IDS[choice]}")
    subprocess.check_call([str(venv_python()), "-c", download], env=env)
    converter = VENV / "Scripts" / "ct2-transformers-converter.exe"
    run([converter, "--model", hf_dir, "--output_dir", out, "--quantization", "int8",
         "--copy_files", "sentencepiece.bpe.model", "--force"])
    shutil.rmtree(hf_dir, ignore_errors=True)
    log(f"Model hazır: {out}")


def download(url: str, dest: Path) -> None:
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    for attempt in range(1, 6):
        log(f"İndiriliyor: {dest.name} (deneme {attempt})")
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(part, "wb") as f:
                shutil.copyfileobj(r, f)
            part.replace(dest)  # yarım dosya hiçbir zaman asıl adla kalmaz
            return
        except OSError as e:
            log(f"İndirme hatası: {e}")
            time.sleep(3 * attempt)
    raise SystemExit(f"{dest.name} indirilemedi; ağ bağlantısını kontrol edip setup.py'yi yeniden çalıştırın.")


def install_font() -> None:
    download(FONT_URL, ASSETS / "NotoSans.ttf")
    download(FONT_LICENSE_URL, ASSETS / "OFL.txt")


def install_paddle() -> None:
    run([venv_python(), "-m", "pip", "install", "-q", *PADDLE_PACKAGES])
    # Modelleri şimdi indir; uygulama çalışırken bu klasörden okunur.
    # Göreli yol: Paddle ASCII dışı mutlak yolları (ör. "Masaüstü") açamıyor.
    script = (
        "from paddleocr import PaddleOCR;"
        "PaddleOCR(lang='japan', use_angle_cls=False, show_log=False,"
        "det_model_dir='models/paddle/det', rec_model_dir='models/paddle/rec',"
        "cls_model_dir='models/paddle/cls')"
    )
    log("PaddleOCR modelleri indiriliyor")
    subprocess.check_call([str(venv_python()), "-c", script], cwd=ROOT)


def write_settings(choice: str) -> None:
    data = {}
    if SETTINGS.exists():
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    data["model"] = choice
    data["model_dir"] = str(model_dir(choice).relative_to(ROOT).as_posix())
    SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Ayar yazıldı: {SETTINGS.name} (model={choice})")


def check_ocr_language() -> None:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]|Out-Null;"
             "[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages|%{$_.LanguageTag}"],
            capture_output=True, text=True, timeout=60,
        ).stdout.split()
    except Exception:
        out = []
    if any(tag.lower().startswith("ja") for tag in out):
        log("Windows OCR Japonca desteği: VAR")
    else:
        log("Windows OCR Japonca desteği: YOK. Yönetici PowerShell'de şunu çalıştırın:")
        log(f"    {OCR_CAPABILITY_CMD}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--paddle", action="store_true", help="PaddleOCR'ı da kur")
    ap.add_argument("--model", choices=sorted(MODEL_IDS), help="RAM ölçümü yerine bu modeli kur")
    args = ap.parse_args()

    ensure_venv()
    choice = choose_model(args.model)
    install_model(choice)
    install_font()
    if args.paddle:
        install_paddle()
    write_settings(choice)
    check_ocr_language()
    log("Bitti. Çalıştırmak için: venv\\Scripts\\python.exe -m src.app")


if __name__ == "__main__":
    main()
