@echo off
REM Launcher dashboard Mesin Transcribe — untuk PowerShell / CMD.
REM Pemakaian:
REM   transcribe.bat                buka di 127.0.0.1:8765 + auto-open browser
REM   transcribe.bat --host 0.0.0.0 akses dari perangkat lain di LAN
cd /d "%~dp0"
.venv\Scripts\python.exe -m src.web.server %*
