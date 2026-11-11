@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python TinNong.py
) else (
  py -3 TinNong.py
)
if errorlevel 1 pause
