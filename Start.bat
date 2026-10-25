:: SPDX-License-Identifier: GPL-3.0-or-later
@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title Multi-Script bridge
cd /d "%~dp0"
REM Start.bat - runs the Multi-Script bridge in THIS window.
REM
REM You normally do not need it: after the one-time Setup.bat the terminal icon in
REM the chat bar starts and stops the bridge for you. Use Start.bat when:
REM   - Setup.bat could not be completed on this PC, or
REM   - you want to watch the bridge's console output yourself.
REM Close this window (or press Ctrl+C) to stop the bridge.
REM Notes are appended to logs\start.log; the bridge's own log is runtime\logs\bridge_debug.log.

if not exist "%~dp0logs" mkdir "%~dp0logs" >nul 2>nul
set "SLOG=%~dp0logs\start.log"
>>"%SLOG%" echo ===== %date% %time%  Start.bat =====
>>"%SLOG%" ver

if not exist "%~dp0runtime\bridge.py" (
    echo.
    echo   ERROR: runtime\bridge.py not found.
    echo   Extract the WHOLE download first ^(right-click, "Extract All..."^), then run Start.bat.
    echo.
    >>"%SLOG%" echo bridge.py missing - unextracted zip?
    pause
    exit /b 1
)

echo "%~dp0" | findstr /i /c:".zip" /c:"\AppData\Local\Temp" >nul 2>nul
if not errorlevel 1 (
    echo.
    echo   This looks like a temporary / zipped location:
    echo     "%~dp0"
    echo   Extract the WHOLE download to a normal folder ^(e.g. Documents^) and run Start.bat there.
    echo.
    >>"%SLOG%" echo refused: running from a zip/temp folder
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
    echo   then run Start.bat again.
    echo.
    >>"%SLOG%" echo python not found
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
)

set "PYV=?"
%PY% -c "import sys; print(sys.version.split()[0])" >"%TEMP%\ms_pyv.txt" 2>nul
if exist "%TEMP%\ms_pyv.txt" set /p PYV=<"%TEMP%\ms_pyv.txt"
del "%TEMP%\ms_pyv.txt" >nul 2>nul
echo.
echo   Multi-Script bridge launcher  ^(Python %PYV%^)
>>"%SLOG%" echo python %PYV% ^(%PY%^)

%PY% -c "import websockets" >nul 2>nul
if errorlevel 1 (
    echo   Installing the one dependency ^(websockets^) - first run only...
    %PY% -m pip install --user websockets
    if errorlevel 1 %PY% -m pip install websockets
    %PY% -c "import websockets" >nul 2>nul
    if errorlevel 1 (
        echo.
        echo   Could not install websockets ^(no internet, firewall, or no pip^).
        echo   Run:  pip install websockets      then start again.
        >>"%SLOG%" echo websockets install failed
        pause
        exit /b 1
    )
)

REM Double-launch check: is a bridge already listening? bridge_status.py tells a bridge of this
REM folder's version (0) from a STALE one - older version or another folder (2) - or a stranger (3).
%PY% "%~dp0runtime\bridge_status.py" --quiet
set "BST=%ERRORLEVEL%"
if "%BST%"=="0" (
    echo.
    echo   A Multi-Script bridge of this version is already running on this PC ^(port 17613^).
    echo   It may have been started by the terminal icon in the chat bar.
    choice /c YN /n /t 12 /d N /m "  Restart it with this window? [y/N] "
    if errorlevel 2 (
        >>"%SLOG%" echo bridge already running - left alone
        exit /b 0
    )
    echo   Restarting...
)
if "%BST%"=="2" (
    echo.
    echo   An OLDER Multi-Script bridge is running on port 17613 ^(from a previous download or folder^).
    echo   It is being replaced by the one in this folder...
    >>"%SLOG%" echo stale bridge on the port - replacing it
)
if "%BST%"=="3" (
    echo.
    echo   Port 17613 is used by a program that is not a Multi-Script bridge.
    echo   Close it, or set ZS_BRIDGE_PORT=17614 before starting.
    >>"%SLOG%" echo port held by a foreign program
)

set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"
set "ZS_STARTED_BY=Start.bat"
echo   Starting the bridge. Close this window or press Ctrl+C to stop it.
echo.
%PY% -u "%~dp0runtime\bridge.py"
set "RC=%ERRORLEVEL%"
echo.
echo   The bridge stopped ^(exit code %RC%^).
>>"%SLOG%" echo bridge exited with code %RC%
if not "%RC%"=="0" echo   See runtime\logs\bridge_debug.log for details, or send it to support.
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
