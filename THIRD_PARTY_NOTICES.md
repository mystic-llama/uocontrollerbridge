# Third-party components

The MIT license covers the application source, including the adapted
Controller Bridge release. The components below keep their own licenses.

- CPython: Python Software Foundation license — https://www.python.org/psf/license/
- pygame-ce: LGPL-2.1-or-later, with bundled components carrying separate notices - https://pypi.org/project/pygame-ce/2.5.8/#files
- SDL and related libraries: see pygame-ce's bundled notices and https://www.libsdl.org/license.php
- pynput: LGPL-3.0 - https://pypi.org/project/pynput/1.8.1/#files
- PySide6 / Shiboken6 and the used Qt Core, Gui, Widgets, Svg components:
  LGPL-3.0 for this distribution - [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html)
  · [PySide6 / Shiboken6 6.10.2 source](https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.10.2)
  · [Qt 6.10.2 source archives](https://download.qt.io/archive/qt/6.10/6.10.2/single/)
- PyInstaller bootloader: GPL with its distribution exception — https://pyinstaller.org/en/stable/license.html

The Windows build includes dependency license files in `licenses/`, including
the LGPLv3 and GPLv3 texts in `licenses/Qt/`.
The application uses dynamically linked, separately shipped Qt libraries. Users
may replace compatible libraries and may reverse engineer the application as
needed to debug modifications to LGPL-covered libraries. Source for the bundled
versions is available from the links above and the versions in `requirements.txt`.
