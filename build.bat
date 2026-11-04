@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Installing Python packages...
python -m pip install --upgrade -r requirements.txt pyinstaller || goto :err
for /f "delims=" %%v in ('python -c "from cliptrim import APP_VERSION as v; print(v)"') do set "VER=%%v"

echo [2/3] Building ClipTrim.exe (v%VER%)...
for /f "delims=" %%i in ('python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"') do set "FF=%%i"
copy /y "%FF%" ffmpeg.exe >nul || goto :err
python -m PyInstaller --noconfirm --clean --windowed --name ClipTrim --icon icon.ico ^
  --add-data "icon.ico;." --add-binary "ffmpeg.exe;." cliptrim.py || goto :err
del ffmpeg.exe

echo [3/3] Building installer...
call :findiscc
if not defined ISCC (
  echo Inno Setup not found - installing it with winget...
  winget install -e --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements
  call :findiscc
)
if not defined ISCC (
  echo Could not find Inno Setup 6. Install it from jrsoftware.org and run build.bat again.
  goto :err
)
"%ISCC%" /Q /DAppVersion=%VER% installer.iss || goto :err

echo.
echo Done: installer\ClipTrim-Setup-%VER%.exe
start "" explorer "%~dp0installer"
pause
exit /b 0

:findiscc
set "ISCC="
for %%p in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe") do (
  if exist "%%~p" set "ISCC=%%~p"
)
exit /b 0

:err
echo.
echo Build failed.
pause
exit /b 1
