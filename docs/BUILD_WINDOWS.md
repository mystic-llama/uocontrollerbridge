# Build on Windows (maintainers only)

Use Windows 10/11 x64, standard CPython 3.12 x64, and Inno Setup 6.
These commands are for the developer, not players:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-build.txt
.\.venv\Scripts\python.exe build_windows.py
```

To run the source application while developing:

```powershell
.\.venv\Scripts\pythonw.exe app.py
```

The release folder contains the Windows Setup EXE, portable ZIP and SHA256SUMS.txt.
The installer creates shortcuts. The installed EXE and its host child use the
Windows GUI subsystem: no command window is needed. The portable ZIP must be
extracted in full; do not move the EXE out of its application folder.

The build uses PyInstaller **onedir**, packaged inside one installer. PyInstaller's
onefile mode extracts into a temporary directory; its documentation advises against
running a onefile executable as administrator. This app supports an explicit
administrator restart, so it uses a folder bundle instead. Build Windows binaries
on Windows; a Linux build is not a Windows executable.

Manual source test command:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

Application startup takes a single-instance lock. Its child owns pygame polling
and input dispatch. The GUI sends atomic control/heartbeat files; the host stops
when the app's heartbeat expires. Stop requests are processed on the polling thread
so input cleanup is ordered. Networking remains on one dedicated socket thread.
The GUI uses asynchronous QProcess/QTimer operations rather than blocking loops.

First check failing builds in the Actions log. For runtime errors, open Support's
settings/logs folder; application-error.log and host-error.log contain tracebacks.
Do not ask players to disable Defender or SmartScreen. Unsigned/new builds may
receive reputation warnings; sign and publish identifiable releases when ready.

Primary references:
- https://pyinstaller.org/en/stable/operating-mode.html
- https://doc.qt.io/qtforpython-6/PySide6/QtCore/QProcess.html
- https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options
