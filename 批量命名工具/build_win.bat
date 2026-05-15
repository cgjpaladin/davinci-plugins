@echo off
cd /d %~dp0
echo === Step 1: Install deps for Python 3.11 ===
py -3.11 -m pip install pywebview bottle pyinstaller -q
if %errorlevel% neq 0 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)

echo === Step 2: Build with PyInstaller (Python 3.11) ===
py -3.11 -m PyInstaller ^
  --onefile --noconsole ^
  --name renamer ^
  --add-data "_build/renamer_web.html;." ^
  --add-data "../shared;shared" ^
  --hidden-import webview ^
  --hidden-import webview.platforms.edgechromium ^
  --hidden-import clr ^
  --hidden-import bottle ^
  --collect-all webview ^
  --collect-all clr ^
  --collect-all bottle ^
  --noconfirm ^
  renamer_web.py

if %errorlevel% neq 0 (
    echo ERROR: PyInstaller build failed
    pause
    exit /b 1
)

echo === Step 3: Copy to Desktop ===
copy /Y dist\renamer.exe "%USERPROFILE%\Desktop\renamer.exe"
if %errorlevel% neq 0 (
    echo ERROR: Copy to Desktop failed
    pause
    exit /b 1
)

echo === DONE ===
echo renamer.exe is on Desktop
pause
