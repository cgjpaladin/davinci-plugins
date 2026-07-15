@echo off
REM 批量命名工具 · 创壹特供版 - Windows 打包脚本 v1.1
REM 用法: build_win.bat
REM 前提: Python 3.11（webview 不支持 >=3.12）+ ffmpeg.exe + Pillow
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM 使用 py -3.11（webview 仅支持 <=3.11）
py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 需要 Python 3.11，请安装后重试
    exit /b 1
)

set HTML_FILE=renamer_web.html
set HTML_BUNDLE=_build\renamer_web.html
set APP_NAME=批量命名工具-创壹特供版-v1.1

REM 清理
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist _build rmdir /s /q _build

REM 拼接 HTML
mkdir _build
py -3.11 _splice.py
if errorlevel 1 ( echo 拼接失败 & exit /b 1 )

REM 打包（仅打包 naming_checks，不拖全量 shared/）
py -3.11 -m PyInstaller ^
  --onefile --noconsole --clean --strip --noupx ^
  --name "%APP_NAME%" ^
  --icon app_icon.ico ^
  --version-file version_info.txt ^
  --add-data "%HTML_BUNDLE%;." ^
  --add-binary "ffmpeg.exe;." ^
  --collect-data webview ^
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

REM 输出到桌面（--onefile 直接出 .exe）
set DESK=%USERPROFILE%\Desktop
copy "dist\%APP_NAME%.exe" "%DESK%\%APP_NAME%.exe" >nul
echo ✅ %APP_NAME%.exe 已输出到桌面
