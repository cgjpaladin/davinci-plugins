@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ═══════════════════════════════════════════
:: 交付自检工具 — Windows 安装脚本（个人版）
:: ═══════════════════════════════════════════

set "PRODUCT=交付自检工具"
set "LOGFILE=%TEMP%\%PRODUCT%_install.log"
echo [%date% %time%] === %PRODUCT% 安装开始 === > "%LOGFILE%"

:: ── 检测管理员权限 ──
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 请右键此文件 →「以管理员身份运行」
    echo 详情见 %LOGFILE%
    pause
    exit /b 1
)

:: ── 查找 Python ──
set "PYTHON="
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
) do (
    if exist %%p if "!PYTHON!"=="" set "PYTHON=%%p"
)
if "%PYTHON%"=="" (
    echo ❌ 未找到 Python 3.11+。请先安装 Python（python.org 下载，勾选「Add to PATH」和「tcl/tk」）
    echo 详情见 %LOGFILE%
    pause
    exit /b 1
)
echo ✅ Python: %PYTHON% >> "%LOGFILE%"

:: ── 目标目录 ──
set "SCRIPT_DIR=%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Fusion\Scripts"
set "TARGET=%SCRIPT_DIR%\Edit\%PRODUCT%"
echo 📂 目标: %TARGET% >> "%LOGFILE%"

:: ── 备份旧版本 ──
if exist "%TARGET%" (
    echo 📋 备份旧版本... >> "%LOGFILE%"
    for /f %%i in ('powershell -Command "Get-Date -Format yyyyMMdd"') do set "TODAY=%%i"
    move "%TARGET%" "%TARGET%_backup_%TODAY%" >nul 2>&1
)

:: ── 解压安装 ──
set "ZIP=%~dp0%PRODUCT%_personal.zip"
if not exist "%ZIP%" (
    echo ❌ 未找到安装包: %ZIP%
    echo 请将 install.bat 与 %PRODUCT%_personal.zip 放在同一目录
    pause
    exit /b 1
)
echo 📦 解压中... >> "%LOGFILE%"
powershell -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%TARGET%' -Force" >> "%LOGFILE%" 2>&1
if %errorlevel% neq 0 (
    echo ❌ 解压失败，查看 %LOGFILE%
    pause
    exit /b 1
)

:: ── Launcher 放到 Scripts/Edit/ ──
echo ⚙ 配置启动器... >> "%LOGFILE%"
(
echo @echo off
echo chcp 65001 ^>nul
echo "%PYTHON%" "%TARGET%\launcher_personal.py"
) > "%SCRIPT_DIR%\Edit\交付自检工具.bat"
echo ✅ Launcher: %SCRIPT_DIR%\Edit\交付自检工具.bat >> "%LOGFILE%"

:: ── 验证 ──
"%PYTHON%" -c "import tkinter" >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠ tkinter 未安装！弹窗将无法使用。请重装 Python 并勾选 tcl/tk 组件。
    echo ⚠ tkinter missing >> "%LOGFILE%"
) else (
    echo ✅ tkinter 可用 >> "%LOGFILE%"
)

:: ── 完成 ──
echo.
echo ✅ %PRODUCT% 安装完成！
echo.
echo 启动方式：DaVinci Resolve → Workspace → Scripts → Edit → 交付自检工具
echo 手动启动: "%SCRIPT_DIR%\Edit\交付自检工具.bat"
echo.
echo 安装日志: %LOGFILE%
echo.
echo ⚠ 首次使用需在 DaVinci Resolve 中启用 External Scripting：
echo   Preferences → System → External Scripting → Local
echo.
pause
