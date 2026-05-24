@echo off
REM 批量命名工具 - Windows 打包脚本
REM 用法: build_win.bat         卡片版
REM       build_win.bat table  表格版
setlocal enabledelayedexpansion
cd /d "%~dp0"

set VARIANT=%1
if "%VARIANT%"=="" set VARIANT=card

if "%VARIANT%"=="table" (
    set JS_FILE=app_table.js
    set HTML_FILE=renamer_table.html
    set HTML_BUNDLE=_build\renamer_table.html
    set APP_NAME=批量命名工具-表格版
) else (
    set JS_FILE=app.js
    set HTML_FILE=renamer_web.html
    set HTML_BUNDLE=_build\renamer_web.html
    set APP_NAME=批量命名工具-卡片版
)

REM 清理
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist _build rmdir /s /q _build

REM 拼接 HTML
mkdir _build
python _splice.py %VARIANT%
if errorlevel 1 ( echo 拼接失败 & exit /b 1 )

REM 打包 (--add-data 在 Windows 用分号分隔)
pyinstaller ^
  --onedir --windowed ^
  --name "批量命名工具" ^
  --icon app_icon.ico ^
  --add-data "%HTML_BUNDLE%;." ^
  --add-data "..\shared;shared" ^
  --collect-data webview ^
  --hidden-import webview ^
  --hidden-import webview.platforms.edgechromium ^
  --hidden-import bottle ^
  --noconfirm ^
  renamer_web.py
if errorlevel 1 ( echo 打包失败 & exit /b 1 )

REM 输出到桌面
set DESK=%USERPROFILE%\Desktop\%APP_NAME%
if exist "%DESK%" rmdir /s /q "%DESK%"
xcopy /e /i /q "dist\批量命名工具" "%DESK%"
echo ✅ %APP_NAME% 已输出到桌面
