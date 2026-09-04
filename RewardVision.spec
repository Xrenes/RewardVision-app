# -*- mode: python ; coding: utf-8 -*-

# One-dir, windowed build. UPX is OFF on purpose: compressing Qt / Python
# DLLs is a common cause of crashes and antivirus false positives on
# machines other than the build host.

import glob
import os
import sys

# Ship the VC++ 2015-2022 runtime DLLs at the bundle root so the app runs
# on a machine that has never had the Visual C++ redistributable
# installed. PySide6 carries its own copies; grab those.
_vc_dlls = []
try:
    import PySide6

    _ps_dir = os.path.dirname(PySide6.__file__)
    for _name in (
        "VCRUNTIME140.dll",
        "VCRUNTIME140_1.dll",
        "MSVCP140.dll",
        "MSVCP140_1.dll",
        "MSVCP140_2.dll",
    ):
        _p = os.path.join(_ps_dir, _name)
        if os.path.exists(_p):
            _vc_dlls.append((_p, "."))
except Exception:
    pass

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=_vc_dlls,
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
