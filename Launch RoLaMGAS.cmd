@echo off
cd /d "%~dp0"
if exist "%~dp0releases\RoLaMGAS.exe" (
    set "ROLAMGAS_DATA_DIR=%~dp0"
    start "" "%~dp0releases\RoLaMGAS.exe"
    exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch GUI.ps1"
if errorlevel 1 pause
