@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set APP_MODE=local
if not exist "app.py" goto wrong_folder
if not exist ".venv\Scripts\python.exe" goto setup
".venv\Scripts\python.exe" -c "import streamlit,pandas,altair,openpyxl,playwright,openai,onnxruntime,tokenizers" >nul 2>nul
if not errorlevel 1 goto launch
:setup
echo Required packages are missing. Running installation first...
call "%~dp0install.cmd" --no-pause
if errorlevel 1 goto failed
:launch
echo Opening AI Operations Dashboard in your browser...
echo Keep this window open while using the workbench. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1 --server.headless=false --server.showEmailPrompt=false --browser.gatherUsageStats=false
if errorlevel 1 goto failed
exit /b 0
:wrong_folder
echo Please extract the complete project first. app.py must be next to this script.
:failed
echo The workbench did not start. Keep this window open and copy the error above.
pause
exit /b 1
