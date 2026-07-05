@echo off
setlocal enabledelayedexpansion

set "TIMESTAMP=%DATE:~6,4%%DATE:~3,2%%DATE:~0,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "TIMESTAMP=%TIMESTAMP: =0%"
set "BK_DIR=bk"
set "TEMP_DIR=%TEMP%\vass_backup_%TIMESTAMP%"
set "ZIP_PATH=%BK_DIR%\vass_%TIMESTAMP%.zip"

if not exist "%BK_DIR%" mkdir "%BK_DIR%"
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"

robocopy "." "%TEMP_DIR%" ^
    /E ^
    /NDL /NFL /NJH /NJS /NS /NC ^
    /XD __pycache__ bk .opencode .git ^
    /XF "*.onnx" "*.onnx.json" ^
    "127_0_0_1_requests.log" "debug.log" "crash.log" "faulthandler.log" "vass.log"

if exist "%TEMP_DIR%\installer\build" rmdir /s /q "%TEMP_DIR%\installer\build"
if exist "%TEMP_DIR%\installer\dist" rmdir /s /q "%TEMP_DIR%\installer\dist"

powershell -NoProfile -Command "Compress-Archive -Path '%TEMP_DIR%\*' -DestinationPath '%ZIP_PATH%' -CompressionLevel Optimal"

rmdir /s /q "%TEMP_DIR%"

echo Backup salvato in %ZIP_PATH%
