$ErrorActionPreference = 'Stop'

python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m PyInstaller --noconfirm --clean --onedir --name MySQLitePatchManager --add-data "templates;templates" --add-data "static;static" portable_entry.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Portable bundle created at dist\MySQLitePatchManager"
