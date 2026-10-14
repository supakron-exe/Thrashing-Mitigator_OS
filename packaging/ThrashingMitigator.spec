from pathlib import Path
root = Path(SPECPATH).parent
a = Analysis(
    [str(root / 'packaging' / 'entry.py')],
    pathex=[str(root), str(root / 'vendor'), str(root / 'packaging')],
    binaries=[], datas=[], hiddenimports=[],
    hookspath=[str(root / 'packaging' / 'hooks')],
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'tkinter', 'matplotlib', 'numpy', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='ThrashingMitigator', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    icon=str(root / 'assets' / 'app.ico'),
    version=str(root / 'packaging' / 'version.txt'),
    uac_admin=False,
)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ThrashingMitigator')
