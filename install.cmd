@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "app.py" goto wrong_folder
if exist ".venv\Scripts\python.exe" goto install_packages
where py >nul 2>nul
if errorlevel 1 goto no_python
py -3.12 -m venv .venv
if errorlevel 1 goto failed
:install_packages
echo Installing workbench dependencies. This may take several minutes.
echo Keep this window open. Installation details are saved in install.log.
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --retries 1 --timeout 30 -r requirements.txt > install.log 2>&1
if errorlevel 1 goto package_failed
".venv\Scripts\python.exe" -c "import streamlit,pandas,altair,openpyxl,playwright,openai,onnxruntime,tokenizers" >> install.log 2>&1
if errorlevel 1 goto package_failed
echo Installing the optional account-reading browser...
".venv\Scripts\python.exe" -m playwright install chromium > browser-install.log 2>&1
if errorlevel 1 echo Browser setup did not finish. Excel analysis is ready; retry install.cmd before reading an account.
echo Installation complete. Double-click start.cmd to open the workbench.
if /i "%~1"=="--no-pause" exit /b 0
pause
exit /b 0
:package_failed
type install.log
echo Installation failed. See install.log in this folder.
goto failed
:no_python
echo Python 3.12 was not found. Install Python 3.12, then run install.cmd again.
goto failed
:wrong_folder
echo Please extract the complete project first. app.py must be next to this script.
:failed
echo Setup did not complete. The workbench has not started.
if /i "%~1"=="--no-pause" exit /b 1
pause
exit /b 1
