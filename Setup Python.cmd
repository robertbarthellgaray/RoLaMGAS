@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Setup complete. Open Launch Mission Search.cmd.
pause
exit /b 0
:failed
echo Setup failed. See the message above. Python 3.12 is recommended.
pause
exit /b 1
