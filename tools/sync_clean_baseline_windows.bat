@echo off
setlocal
cd /d "%~dp0\.."
where git >nul 2>nul
if errorlevel 1 (
  echo Git is not installed. Install Git for Windows or GitHub Desktop first.
  exit /b 1
)
if not exist .git git init
git remote get-url origin >nul 2>nul
if errorlevel 1 git remote add origin https://github.com/barod1986-ship-it/MMOARAB.git
git fetch origin main
git checkout -B setup/stage-292-baseline-import origin/main
where py >nul 2>nul
if not errorlevel 1 (
  py -3 tools\validate_repository.py
) else (
  python tools\validate_repository.py
)
if errorlevel 1 exit /b 1
git add -A
git commit -m "chore: import clean stage 292 baseline"
git push -u origin setup/stage-292-baseline-import
echo.
echo Baseline branch uploaded. Open a Pull Request into main after reviewing the diff.
endlocal
