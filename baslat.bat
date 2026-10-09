@echo off
rem Çift tıklayınca uygulamayı başlatır (hangi klasörden açıldığı önemli değil).
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo venv bulunamadi. Once kurulum yapin:  py -3.11 setup.py
    pause
    exit /b 1
)
"venv\Scripts\python.exe" -m src.app %*
if errorlevel 1 pause
