# -*- mode: python ; coding: utf-8 -*-

# One-dir, windowed build. UPX is OFF on purpose: compressing Qt / Python
# DLLs is a common cause of crashes and antivirus false positives on
# machines other than the build host.

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=[("examples/hazmob/*.png", "examples/hazmob")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "pytest",
        "setuptools",
        "pip",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RewardVision",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="RewardVision",
)
