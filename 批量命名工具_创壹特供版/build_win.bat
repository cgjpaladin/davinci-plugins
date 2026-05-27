@echo off
REM 批量命名工具 · 创壹特供版 - Windows 打包脚本 v1.0
REM 用法: build_win.bat
REM 前提: Python 3.11-3.12（webview 不支持 >=3.13）+ ffmpeg.exe + Pillow
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Python 版本检测（webview 仅支持 <=3.12）
python --version 2>&1 | findstr /r "3\.1[12]\." >nul
if errorlevel 1 (
    echo ❌ 需要 Python 3.11-3.12，当前版本:
    python --version
    echo 请安装 Python 3.11 或 3.12，或使用 py -3.11 命令
    exit /b 1
)

set HTML_FILE=renamer_web.html
set HTML_BUNDLE=_build\renamer_web.html
set APP_NAME=批量命名工具-创壹特供版-v1.0

REM 清理
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist _build rmdir /s /q _build

REM 拼接 HTML
mkdir _build
python _splice.py
if errorlevel 1 ( echo 拼接失败 & exit /b 1 )

REM 打包 (--add-data 在 Windows 用分号分隔)
pyinstaller ^
  --onedir --windowed --clean ^
  --name "%APP_NAME%" ^
  --icon app_icon.ico ^
  --version-file version_info.txt ^
  --add-data "%HTML_BUNDLE%;." ^
  --add-data "..\shared;shared" ^
  --add-binary "ffmpeg.exe;." ^
  --collect-data webview ^
  --hidden-import webview ^
  --hidden-import webview.platforms.edgechromium ^
  --hidden-import bottle ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageOps ^
  --noconfirm ^
  renamer_web.py
if errorlevel 1 ( echo 打包失败 & exit /b 1 )

REM Windows 图标缓存绕过：先用临时名再改名
set DESK=%USERPROFILE%\Desktop
set TMPEXE="%DESK%\_%APP_NAME%.exe"
if exist %TMPEXE% del /f /q %TMPEXE%
copy "dist\%APP_NAME%\%APP_NAME%.exe" %TMPEXE% >nul
ping 127.0.0.1 -n 2 >nul
move /Y %TMPEXE% "%DESK%\%APP_NAME%.exe" >nul

REM 输出文件夹
set DST="%DESK%\%APP_NAME%"
if exist %DST% rmdir /s /q %DST%
xcopy /e /i /q "dist\%APP_NAME%" %DST%
echo ✅ %APP_NAME% 已输出到桌面
