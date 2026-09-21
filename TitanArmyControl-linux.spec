# -*- mode: python ; coding: utf-8 -*-

import pathlib
import sys

python_lib = pathlib.Path(sys.prefix) / 'lib'
tk_binaries = [(str(path), '.') for name in ('libtcl9.0.so', 'libtcl9tk9.0.so')
               if (path := python_lib / name).is_file()]

a = Analysis(
    ['run_app.py'],
    pathex=['.'],
    binaries=tk_binaries,
    datas=[('TitanArmyControl/ta-logo-white.png', '.'),
           ('TitanArmyControl/ta-icon-black.png', '.'),
           ('TitanArmyControl/tray_helper.py', 'TitanArmyControl'),
           ('TitanArmyControl/hdr_helper.py', 'TitanArmyControl')],
    hiddenimports=['TitanArmyControl.linux_backend'],
    excludes=['TitanArmyControl.windows_backend', 'pystray', 'PIL', 'numpy'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='TitanArmyControl-linux',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='TitanArmyControl/ta-icon-black.png',
)
