@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
".venv\Scripts\python.exe" main.py
