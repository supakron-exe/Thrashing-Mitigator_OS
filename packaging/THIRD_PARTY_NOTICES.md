# Third-party components

This portable application bundles dynamically linked Python 3.11, PySide6/Qt 6.7.2, shiboken6, psutil, keyboard, qrcode and Pillow, including their runtime dependencies. Exact versions and source/executable fingerprints are in BUILD_INFO.json and SOURCE_HASHES.json. Dependency metadata and applicable license texts are in LICENSES.

- FluentUI: MIT. Copyright zhuzichu; the unchanged original notice is in LICENSES/FluentUI-MIT.txt. Local modifications are documented in LICENSES/FluentUI-LOCAL-PATCHES.md. Pinned source: https://github.com/zhuzichu520/PySide6-FluentUI-QML/tree/617986a17c9850ecb365bc02713433abab79c7aa
- Python: Python Software Foundation license; LICENSES/Python.txt. Source: https://www.python.org/downloads/source/
- PySide6 and shiboken6: Qt for Python 6.7.2. License information and source: https://code.qt.io/cgit/pyside/pyside-setup.git/tree/?h=v6.7.2
- Qt runtime libraries and QML modules: Qt 6.7.2. LGPL-3.0, GPL-3.0 and the Qt GPL exception texts are included in LICENSES, together with the package's license notices. Corresponding upstream source archives: https://download.qt.io/archive/qt/6.7/6.7.2/submodules/
- Other components: upstream license texts and package metadata in LICENSES. PyInstaller's bootloader has its distribution exception.

Qt libraries remain separate under _internal/PySide6. You may replace them with compatible builds and exercise the modification, relinking and reverse-engineering rights provided by their applicable licenses. This package does not impose additional restrictions on those rights.

The application's current source, modified FluentUI source, resource manifests and rebuild scripts are maintained in the main Thrashing-Mitigator project folder. Rebuild instructions are in docs/PACKAGING.md and requirements-build.txt there. They are not duplicated as a Source.zip in this portable package; request the source project folder from its distributor if needed. User configuration, logs and history are not included in this package.
