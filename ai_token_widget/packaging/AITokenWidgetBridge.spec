# PyInstaller spec for the console bridge executable.
# It shares the generated icon/version assets with the GUI build.

from pathlib import Path

PACKAGING = Path(SPECPATH).resolve()
PROJECT = PACKAGING.parent
REPO = PROJECT.parent
ASSETS = PROJECT / "build" / "assets"

if not (ASSETS / "icon.ico").exists():
    raise SystemExit(
        "Missing generated assets. Run packaging/build.ps1 instead of invoking "
        "PyInstaller directly."
    )

a = Analysis(
    [str(PACKAGING / "launcher_bridge.py")],
    pathex=[str(REPO)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AITokenWidgetBridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ASSETS / "icon.ico"),
    version=str(ASSETS / "version_info_bridge.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AITokenWidgetBridge",
)
