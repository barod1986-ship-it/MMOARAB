@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

where git >nul 2>nul
if errorlevel 1 (
  echo Git is not installed. Install Git for Windows or GitHub Desktop first.
  exit /b 1
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 tools\import_clean_baseline.py
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3 is not installed or is not available in PATH.
    exit /b 1
  )
  python tools\import_clean_baseline.py
)

if errorlevel 1 exit /b 1

echo.
echo Finished. Review the uploaded branch and open the Pull Request link printed above.
endlocal
