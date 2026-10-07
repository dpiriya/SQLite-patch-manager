# My SQLite Patch Manager

An offline-first, single-user Flask app for comparing a Patch SQLite database with a Base database, inspecting schema and row changes, and merging selected changes into a separate copy of Base.

## Requirements


## Run from source

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000` in a browser. The server binds to loopback only. Uploads are held in the app's local `instance/jobs` folder while the process is running. Starting a new comparison removes the prior comparison's temporary files.

## Tests

```powershell
python -m pytest -q
```

Tests use temporary SQLite databases and verify primary-key matching, schema and CRUD reporting, merge options, integrity, and preservation of the uploaded Base file.

## Build a portable Windows folder

On a Windows build machine with Python and the packages available:

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller
.\build_windows.ps1
```

The script builds a PyInstaller onedir package at `dist\MySQLitePatchManager`. Copy that whole folder to USB and run `MySQLitePatchManager.exe`; it includes the Python runtime and Flask dependencies. The app starts its local server and opens the browser. Close the console with `Ctrl+C` to stop it. Building requires Python on the build machine, but running the resulting folder does not require Python or internet access.

## Merge behavior

