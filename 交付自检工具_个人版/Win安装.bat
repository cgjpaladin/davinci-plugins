@echo off
setlocal enabledelayedexpansion
set "PYTHON="
for %%p in (
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
) do (
    if exist %%p if "!PYTHON!"=="" set "PYTHON=%%p"
)
if "%PYTHON%"=="" (
    echo Python 3.11+ not found. Install from python.org
    pause
    exit /b 1
)
echo Python: %PYTHON%
echo Running install...
call "%PYTHON%" "%~dp0install.py"
pause
