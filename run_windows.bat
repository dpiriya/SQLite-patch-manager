@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Development Python environment not found. For a portable USB build, run MySQLitePatchManager.exe from the dist folder.
  pause
  exit /b 1
)
start "My SQLite Patch Manager" http://127.0.0.1:5000
".venv\Scripts\python.exe" app.py
