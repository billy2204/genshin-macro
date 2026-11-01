@echo off
REM Build everything:
REM   dist\GenshinMacro\            onedir build (used by the installer)
REM   dist\GenshinMacroSetup.exe    Inno Setup installer
REM   dist\GenshinMacro.exe         portable single-file build
cd /d "%~dp0"
python -m pip install -q -r requirements.txt

for /f "delims=" %%v in ('python -c "from genshin_macro.updater import APP_VERSION; print(APP_VERSION)"') do set VER=%%v
echo Version %VER%

python -m PyInstaller --noconfirm --onedir --noconsole --uac-admin --name GenshinMacro main.py || goto :err
python -m PyInstaller --noconfirm --onefile --noconsole --uac-admin --name GenshinMacro --distpath dist\portable main.py || goto :err
copy /y dist\portable\GenshinMacro.exe dist\GenshinMacro.exe >nul

set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  %ISCC% /Q /DAppVersion=%VER% installer\GenshinMacro.iss || goto :err
) else (
  echo Inno Setup not found - skipping installer. Install with: winget install JRSoftware.InnoSetup
)

(
  echo {"version": "%VER%", "url": "https://github.com/billy2204/genshin-macro/releases/latest/download/GenshinMacroSetup.exe", "portable": "https://github.com/billy2204/genshin-macro/releases/latest/download/GenshinMacro.exe"}
) > dist\manifest.json

echo.
echo Done:
dir /b dist\GenshinMacroSetup.exe dist\GenshinMacro.exe dist\manifest.json
exit /b 0
:err
echo BUILD FAILED
exit /b 1
