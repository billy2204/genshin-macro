@echo off
REM Build a single-file, admin-requesting exe into dist\GenshinMacro.exe
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --onefile --noconsole --uac-admin --name GenshinMacro main.py
echo.
echo Done: dist\GenshinMacro.exe
pause
