# -*- mode: python ; coding: utf-8 -*-

import os
import subprocess
import sys

# 动态定位 OpenCV 自带的人脸级联模型，避免把本机绝对路径写死在仓库里
_here = os.path.dirname(os.path.abspath(SPEC))
_cascade = subprocess.run(
    [sys.executable, os.path.join(_here, 'face_guard.py'), '--cascade-path'],
    capture_output=True, text=True, check=True,
).stdout.strip()

a = Analysis(
    ['face_guard.py'],
    pathex=[],
    binaries=[],
    datas=[(_cascade, '.'),
           ('assets', 'assets')],
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
    a.binaries,
    a.datas,
    [],
    name='FaceGuard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
