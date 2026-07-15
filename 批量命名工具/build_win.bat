@echo off
REM 批量命名工具 - Windows 打包脚本 (v3.7.13)
REM 用法: build_win.bat table  表格版（推荐）
REM       build_win.bat        卡片版（备用）
REM 前提: Python 3.13 + pywebview 6.2.1 + ffmpeg.exe 在项目目录
setlocal enabledelayedexpansion
cd /d "%~dp0"

set VARIANT=%1
if "%VARIANT%"=="" set VARIANT=table

REM Python 版本检测
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 未安装
    exit /b 1
)

if "%VARIANT%"=="table" (
    set HTML_BUNDLE=_build\renamer_table.html
    set APP_NAME=批量命名工具-v3.7.13
) else (
    set HTML_BUNDLE=_build\renamer_web.html
    set APP_NAME=批量命名工具-卡片版-v3.7.13
)

REM 清理
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist _build rmdir /s /q _build

REM 拼接 HTML
mkdir _build
python _splice.py %VARIANT%
if errorlevel 1 ( echo 拼接失败 & exit /b 1 )

REM 打包 --onefile（方案C：单文件 + 首次运行自安装）
python -m PyInstaller ^
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
  --hidden-import PIL.PngImagePlugin ^
  --hidden-import PIL._webp ^
  --hidden-import openpyxl ^
  --hidden-import openpyxl.utils ^
  --hidden-import openpyxl.drawing.image ^
  --hidden-import tkinter ^
  --hidden-import tkinter.filedialog ^
  --collect-all webview ^
  --collect-all clr ^
  --collect-all bottle ^
  --collect-all openpyxl ^
  --noconfirm ^
  renamer_web.py
if errorlevel 1 ( echo 打包失败 & exit /b 1 )

echo ✅ 构建成功: dist\%APP_NAME%.exe
echo 产物路径: %CD%\dist\%APP_NAME%.exe
