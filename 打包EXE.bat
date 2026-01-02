@echo off
chcp 65001 >nul
echo ====================================
echo   待办提醒应用 - 打包成 EXE
echo ====================================
echo.

cd /d "%~dp0"

echo [1/2] 检查 PyInstaller...
python -c "import PyInstaller" 2>nul
if %errorlevel% neq 0 (
    echo PyInstaller 未安装，正在安装...
    pip install pyinstaller
)

echo.
echo [2/2] 正在打包应用...
echo 这可能需要几分钟时间，请耐心等待...
echo.

pyinstaller --onefile --windowed --name="待办提醒" --icon=NONE todo_app.py

if %errorlevel% equ 0 (
    echo.
    echo ====================================
    echo   打包完成！
    echo ====================================
    echo.
    echo EXE 文件位置: %cd%\dist\待办提醒.exe
    echo.
    echo 你可以将这个文件复制到任何地方运行
    echo.

    explorer dist
) else (
    echo.
    echo 打包失败！请检查错误信息。
    echo.
)

pause
