@echo off
cd /d "%~dp0"
set APP_MODE=local
if not exist ".venv\Scripts\python.exe" (
    echo Please run install.cmd first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1 --server.showEmailPrompt=false --browser.gatherUsageStats=false
if errorlevel 1 pause
