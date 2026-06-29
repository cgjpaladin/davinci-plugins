@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  错误日志（放在 bat 旁边，安装成功自动删除）
:: ============================================================
set "ERRFILE=%~dp0如果安装失败就把这个发给作者.txt"
echo ========== 安装日志 %date% %time% ========== > "%ERRFILE%"
echo 系统: %OS%  计算机: %COMPUTERNAME%  用户: %USERNAME% >> "%ERRFILE%"

:: ============================================================
::  欢迎
:: ============================================================
echo.
echo ========================================
echo   交付自检工具 v2.5.8
echo   针对短剧/影视成片的自动化质检插件
echo   作者：电影裁缝 Bryan（微信 paladinpp）
echo ========================================
echo.
echo   [*] 正在检测系统环境...

:: ============================================================
::  1. 管理员权限
:: ============================================================
net session >nul 2>&1
if !errorlevel! neq 0 (
    echo   [X] 请右键"Win安装.bat"→"以管理员身份运行"
    echo [失败] 没有管理员权限 >> "%ERRFILE%"
    pause
    exit /b 1
)
echo [  OK  ] 管理员权限 >> "%ERRFILE%"

:: ============================================================
::  2. 查找 Python
:: ============================================================
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
    if exist "%%p" if "!PYTHON!"=="" set "PYTHON=%%p"
)

if not "!PYTHON!"=="" (
    for /f "tokens=*" %%v in ('!PYTHON! --version 2^>^&1') do set "PYVER=%%v"
    echo [  OK  ] Python: !PYVER! ^(!PYTHON!^) >> "%ERRFILE%"
    set "NEED_PYTHON=0"
    goto :verify_python
)
echo [  ..  ] Python 未找到，搜索路径: %ProgramFiles%\Python31x 等 >> "%ERRFILE%"

:: ============================================================
::  3. 自动安装 Python
:: ============================================================
set "NEED_PYTHON=1"
echo [  ..  ] 安装 Python 3.13... >> "%ERRFILE%"

powershell -Command "Expand-Archive -Path '%~dp0data.zip' -DestinationPath '%TEMP%\pyextract' -Force" >> "%ERRFILE%" 2>&1
set "PYINST="
for /r "%TEMP%\pyextract" %%f in (python-3.13.13-amd64.exe) do if "!PYINST!"=="" set "PYINST=%%f"

if not "!PYINST!"=="" (
    echo [  OK  ] 使用离线安装器 >> "%ERRFILE%"
) else (
    echo [  OK  ] 未找到离线安装器 >> "%ERRFILE%"
)

if "!PYINST!"=="" (
    echo   [X] 无法获取 Python 安装器，请检查 data.zip 完整性
    echo [失败] 无法获取 Python 安装器 >> "%ERRFILE%"
    pause
    exit /b 1
)

"!PYINST!" /quiet InstallAllUsers=1 PrependPath=1 Include_tcltk=1 >> "%ERRFILE%" 2>&1
timeout /t 30 >nul

if exist "%TEMP%\pyextract" powershell -Command "Remove-Item '%TEMP%\pyextract' -Recurse -Force" >> "%ERRFILE%" 2>&1

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
    if exist "%%p" if "!PYTHON!"=="" set "PYTHON=%%p"
)

if "!PYTHON!"=="" (
    echo   [X] Python 安装失败
    echo [失败] Python 安装后仍未找到 >> "%ERRFILE%"
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('!PYTHON! --version 2^>^&1') do set "PYVER=%%v"
echo [  OK  ] Python 安装成功: !PYVER! >> "%ERRFILE%"

:verify_python
:: ============================================================
::  4. 验证 tkinter
:: ============================================================
!PYTHON! -c "import tkinter" >> "%ERRFILE%" 2>&1
if !errorlevel! neq 0 (
    echo   [X] tkinter 不可用，请重新安装 Python 并勾选 tcl/tk
    echo [失败] tkinter 不可用 >> "%ERRFILE%"
    pause
    exit /b 1
)
echo [  OK  ] tkinter 可用 >> "%ERRFILE%"

:: ============================================================
::  5. 检查 data.zip
:: ============================================================
if not exist "%~dp0data.zip" (
    echo   [X] 未找到 data.zip
    echo [失败] 未找到 data.zip，路径: %~dp0 >> "%ERRFILE%"
    pause
    exit /b 1
)
echo [  OK  ] 找到 data.zip >> "%ERRFILE%"

:: ============================================================
::  6. 检测 DaVinci Resolve
:: ============================================================
set "DR_OK=0"
echo [  ..  ] 检查: %%PROGRAMDATA%%\Blackmagic Design\DaVinci Resolve >> "%ERRFILE%"
if exist "%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve" (
    set "DR_OK=1"
    echo [  OK  ] DaVinci Resolve 已安装 >> "%ERRFILE%"
    set "DR_SCRIPTING_NEEDS_FIX=0"
    set "DC=%APPDATA%\Blackmagic Design\DaVinci Resolve\Preferences\config.dat"
    if exist "!DC!" (
        findstr /c:"System.Scripting.Mode = 0" "!DC!" >nul 2>&1 && set "DR_SCRIPTING_NEEDS_FIX=1"
    )
) else (
    echo [  ^!^!  ] 未检测到达芬奇 Resolve >> "%ERRFILE%"
)

:: ============================================================
::  环境检测完成，显示摘要
:: ============================================================
echo.
echo   将进行以下操作：
echo     [*] 安装插件到 DaVinci Resolve
if "!NEED_PYTHON!"=="1" echo     [*] 安装 Python 3.13
if "!DR_SCRIPTING_NEEDS_FIX!"=="1" echo     [*] 启用达芬奇外部脚本权限
echo.
echo   按任意键开始安装，关闭窗口取消...
pause >nul
echo.

:: ============================================================
::  7. 解压
:: ============================================================
if "!DR_OK!"=="0" (
    echo   [X] 未检测到达芬奇 Resolve，无法继续安装
    echo [失败] DaVinci Resolve 未安装 >> "%ERRFILE%"
    pause
    exit /b 1
)
set "SCRIPTS=%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Fusion\Scripts"
echo [  ..  ] 解压 data.zip ^(约 95MB^)... >> "%ERRFILE%"
!PYTHON! -c "import zipfile; zipfile.ZipFile(r'%~dp0data.zip').extractall(r'%SCRIPTS%')" >> "%ERRFILE%" 2>&1
if !errorlevel! neq 0 (
    echo   [X] 解压失败
    echo [失败] 解压失败，错误代码: !errorlevel! >> "%ERRFILE%"
    pause
    exit /b 1
)
echo [  OK  ] 解压完成 >> "%ERRFILE%"

:: ============================================================
::  8. 修复中文目录名
:: ============================================================
!PYTHON! -c "import os,shutil; s=r'%SCRIPTS%'; P='\u4ea4\u4ed8\u81ea\u68c0\u5de5\u5177'; t=os.path.join(s,P); [os.rename(os.path.join(s,n),t) for n in os.listdir(s) if os.path.isdir(os.path.join(s,n)) and os.path.isdir(os.path.join(s,n,'shared')) and n^!=P]" >> "%ERRFILE%" 2>&1
echo [  OK  ] 目录名已修复 >> "%ERRFILE%"

:: ============================================================
::  9. 创建 Launcher
:: ============================================================
set "LP=%SCRIPTS%\Edit\交付自检工具.py"
echo [  ..  ] Launcher 目标: %SCRIPTS%\Edit\交付自检工具.py >> "%ERRFILE%"
mkdir "%SCRIPTS%\Edit" 2>nul

> "%LP%" echo import subprocess,os,sys
>> "%LP%" echo try:
>> "%LP%" echo   _HERE=os.path.dirname(os.path.abspath(__file__^)^)
>> "%LP%" echo except NameError:
>> "%LP%" echo   _HERE=os.path.dirname(os.path.realpath(sys.argv[0]^)^)
>> "%LP%" echo _IDIR=os.path.join(_HERE,"..","\u4ea4\u4ed8\u81ea\u68c0\u5de5\u5177"^)
>> "%LP%" echo _LP=os.path.join(_IDIR,"launcher_personal.py"^)
>> "%LP%" echo _ENV=os.environ.copy(^)
>> "%LP%" echo _ENV["PYTHONIOENCODING"]="utf-8"
>> "%LP%" echo _ENV["PYTHONUTF8"]="1"
>> "%LP%" echo _ENV["WORKBUDDY_PERSONAL"]="1"
>> "%LP%" echo _PY=sys.executable
>> "%LP%" echo subprocess.Popen([_PY,"-B",_LP],env=_ENV^)

if not exist "%LP%" (
    echo   [X] Launcher 创建失败
    echo [失败] Launcher 创建失败 >> "%ERRFILE%"
    pause
    exit /b 1
)
echo [  OK  ] Launcher 已创建 >> "%ERRFILE%"

:: ============================================================
::  10. 初始化 .env
:: ============================================================
set "TOOLDIR=%SCRIPTS%\交付自检工具"
if not exist "%TOOLDIR%\.env" (
    if exist "%TOOLDIR%\.env.example" (
        copy "%TOOLDIR%\.env.example" "%TOOLDIR%\.env" >nul 2>&1
        echo [  OK  ] .env 已初始化 >> "%ERRFILE%"
    ) else (
        echo [  ^!^!  ] .env.example 不存在 >> "%ERRFILE%"
    )
) else (
    echo [  OK  ] .env 已存在，保留 >> "%ERRFILE%"
)

!PYTHON! "%TOOLDIR%\shared\_write_env.py" >> "%ERRFILE%" 2>&1
echo [  OK  ] License URL 已写入 >> "%ERRFILE%"

for /r "%TOOLDIR%" %%d in (__pycache__) do if exist "%%d" rmdir /s /q "%%d" 2>nul
echo [  OK  ] __pycache__ 已清理 >> "%ERRFILE%"

:: ============================================================
::  11. 启用 External Scripting
:: ============================================================
if "!DR_SCRIPTING_NEEDS_FIX!"=="1" (
    powershell -Command "(Get-Content '%DC%' -Encoding UTF8) -replace 'System\.Scripting\.Mode = 0','System.Scripting.Mode = 1' | Set-Content '%DC%' -Encoding UTF8" >> "%ERRFILE%" 2>&1
    if !errorlevel! equ 0 (
        echo [  OK  ] External Scripting 已启用 >> "%ERRFILE%"
    ) else (
        echo [  ^!^!  ] External Scripting 设置失败 >> "%ERRFILE%"
    )
) else (
    echo [  OK  ] External Scripting 已启用 ^(无需修改^) >> "%ERRFILE%"
)

:: ============================================================
::  12. 验证
:: ============================================================
set "PASS=1"
if not exist "%TOOLDIR%\ui.py" (
    echo [失败] ui.py 缺失 >> "%ERRFILE%"
    set "PASS=0"
)
if not exist "%LP%" (
    echo [失败] 启动器缺失 >> "%ERRFILE%"
    set "PASS=0"
)

if "!PASS!"=="1" (
    !PYTHON! -c "import sys; sys.path.insert(0,r'%TOOLDIR%'); sys.path.insert(0,r'%TOOLDIR%\shared'); import config,check_core; print('验证通过 v'+config.version_string())" >> "%ERRFILE%" 2>&1
    if !errorlevel! neq 0 (
        echo [失败] Python 模块导入失败 >> "%ERRFILE%"
        set "PASS=0"
    )
)

if "!PASS!"=="1" (
    echo [验证] 全部通过 >> "%ERRFILE%"
) else (
    echo [验证] 有检查未通过 >> "%ERRFILE%"
)

:: ============================================================
::  13. 完成
:: ============================================================
if "!PASS!"=="0" (
    echo.
    echo   [X] 安装未通过验证
    echo   请把同目录下的"如果安装失败就把这个发给作者.txt"
    echo   发送给微信 paladinpp
    echo.
    pause
    exit /b 1
)

del "%ERRFILE%" 2>nul

echo.
echo   安装完成
echo.
echo   使用方法：
echo   DaVinci Resolve → Workspace → Scripts
echo   → Edit → 交付自检工具
echo.
pause