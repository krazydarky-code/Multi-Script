:: SPDX-License-Identifier: GPL-3.0-or-later
@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title Multi-Script one-time setup
cd /d "%~dp0"
REM One-time setup. Registers the "terminal" launcher with your browser so the
REM terminal icon in the Multi-Script chat bar can start/stop the bridge itself.
REM Safe to re-run any time. If anything fails, Start.bat still runs the bridge.
REM A full transcript is written to logs\setup.log.
REM
REM Run this once for a new download / new folder to register THIS installation.
REM Signed in-place auto-updates rerun launcher setup and verify it automatically.
REM If Updates says "Finish setup", use that action or run this file again.
REM Options: --keep-running, --no-start. No settings are reset.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist "%~dp0runtime\install_native_host.py" (
    echo.
    echo   ERROR: runtime\install_native_host.py not found.
    echo   Extract the WHOLE download first ^(right-click, "Extract All..."^), then run Setup.bat.
    echo.
    pause
    exit /b 1
)

echo "%~dp0" | findstr /i /c:".zip" /c:"\AppData\Local\Temp" >nul 2>nul
if not errorlevel 1 (
    echo.
    echo   This looks like a temporary / zipped location:
    echo     "%~dp0"
    echo   Extract the WHOLE download to a normal folder ^(e.g. Documents^) and run Setup.bat there,
    echo   otherwise the registration breaks as soon as the temp folder is cleaned.
    echo.
    pause
    exit /b 1
)

call :findpy
if not defined PY (
    echo.
    echo   Python 3.9 or newer was not found.
    where winget >nul 2>nul
    if not errorlevel 1 (
        echo   Trying to install it with winget ^(this can take a minute^)...
        winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
        call :findpy
    )
)
if not defined PY (
    echo.
    echo   Install Python from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^),
    echo   then run Setup.bat again.
    echo.
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
)

REM --no-pause: this file pauses once itself, so Python must not also wait for Enter.
echo.
echo   Multi-Script setup - folder: %~dp0
call %PY% "%~dp0runtime\install_native_host.py" --no-pause %*
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" (
    REM 6.28: best-effort engine prerequisites (uv for Unity/Blender, BlenderMCP
    REM add-on download, bundled Blender config entry). Never fails setup.
    call %PY% "%~dp0runtime\setup_engines.py"
)
echo.
if "%RC%"=="0" (
    echo   Final check:
    call %PY% "%~dp0runtime\bridge_status.py"
    echo   Now reload the Multi-Script extension in chrome://extensions ^(or edge://extensions^) and refresh your AI chat tab.
)
if not "%RC%"=="0" (
    echo   Setup did not finish ^(code %RC%^). Read the message above.
    echo   A transcript was saved to: %~dp0logs\setup.log
    echo   You can still run the bridge directly: double-click Start.bat
)
pause
exit /b %RC%

:findpy
set "PY="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; assert sys.version_info>=(3,9)" >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)
if defined PY goto :eof
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; assert sys.version_info>=(3,9)" >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if defined PY goto :eof
for %%R in ("%LOCALAPPDATA%\Programs\Python" "%ProgramFiles%" "%ProgramFiles(x86)%") do (
    for /f "delims=" %%D in ('dir /b /ad /o-n "%%~R\Python3*" 2^>nul') do call :trypy "%%~R\%%D\python.exe"
)
goto :eof

:trypy
if defined PY goto :eof
if not exist %1 goto :eof
%1 -c "import sys; assert sys.version_info>=(3,9)" >nul 2>nul
if not errorlevel 1 set PY=%1
goto :eof
