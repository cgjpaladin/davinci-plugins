@echo off
chcp 65001 >nul
set "SRC=%~2"
if "%SRC%"=="" set "SRC=%~1"
if "%SRC%"=="" (echo SRC_MISSING>"%PROGRAMDATA%\deli_update_result.txt" & exit /b 2)
set "DST=%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\交付自检工具"
if not exist "%DST%" mkdir "%DST%"
robocopy "%SRC%" "%DST%" /E /NFL /NDL /NJH /NJS /nc /ns /np >nul
if errorlevel 8 (echo FAILED>"%PROGRAMDATA%\deli_update_result.txt" & exit /b 1)
echo OK>"%PROGRAMDATA%\deli_update_result.txt"
exit /b 0
