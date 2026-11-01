@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" mission_search.py wizard
) else (
  python mission_search.py wizard
)
pause
