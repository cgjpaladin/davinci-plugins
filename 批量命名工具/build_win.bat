@echo off
REM 批量命名工具 - Windows 打包脚本 (v3.6)
REM 用法: build_win.bat table  表格版（推荐）
REM       build_win.bat        卡片版（备用）
REM 前提: Python 3.11（webview 不支持 ≥3.12）+ ffmpeg.exe 在项目目录
setlocal enabledelayedexpansion
cd /d "%~dp0"

set VARIANT=%1
if "%VARIANT%"=="" set VARIANT=table

REM 使用 py -3.11（webview 仅支持 ≤3.11）
py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 需要 Python 3.11，请安装后重试
    exit /b 1
)

if "%VARIANT%"=="table" (
    set JS_FILE=app_table.js
    set HTML_FILE=renamer_table.html
    set HTML_BUNDLE=_build\renamer_table.html
    set APP_NAME=批量命名工具-v3.6
) else (
    set JS_FILE=card\app.js
    set HTML_FILE=card\renamer_web.html
    set HTML_BUNDLE=_build\renamer_web.html
    set APP_NAME=批量命名工具-卡片版-v3.6
)

REM 清理
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist _build rmdir /s /q _build

REM 拼接 HTML
mkdir _build
py -3.11 _splice.py %VARIANT%
if errorlevel 1 ( echo 拼接失败 & exit /b 1 )

REM 打包 (--add-data 在 Windows 用分号分隔)
py -3.11 -m PyInstaller ^
  --onefile --windowed --clean --noconsole ^
  --name "%APP_NAME%" ^
  --icon app_icon.ico --version-file version_info.txt ^
  --add-data "%HTML_BUNDLE%;." ^
  --add-data "..\shared;shared" ^
  --add-binary "ffmpeg.exe;." ^
  --hidden-import webview ^
  --hidden-import webview.platforms.edgechromium ^
  --hidden-import clr ^
  --hidden-import bottle ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageOps ^
  --hidden-import openpyxl ^
  --hidden-import openpyxl.utils ^
  --hidden-import openpyxl.drawing.image ^
  --collect-all webview ^
  --collect-all clr ^
  --collect-all bottle ^
  --collect-all openpyxl ^
  --noconfirm ^
  renamer_web.py
if errorlevel 1 ( echo 打包失败 & exit /b 1 )

REM 输出到桌面
set DESK=%USERPROFILE%\Desktop
copy "dist\%APP_NAME%.exe" "%DESK%\%APP_NAME%.exe" >nul
echo ✅ %APP_NAME%.exe 已输出到桌面

REM 更新包（用于自动更新）
set UPDATE_ZIP=%DESK%\batch_renamer_win.zip
powershell -Command "Compress-Archive -Path '%DESK%\%APP_NAME%.exe' -DestinationPath '%UPDATE_ZIP%' -Force" >nul 2>&1
if exist "%UPDATE_ZIP%" (
    echo ✅ 更新包: %UPDATE_ZIP%
    certutil -hashfile "%UPDATE_ZIP%" SHA256 | findstr /v "hash" > "%UPDATE_ZIP%.sha256"
) else (
    echo ⚠ 更新包创建失败
)
