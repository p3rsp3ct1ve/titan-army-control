# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run_app.py'],
    pathex=['.'],
    binaries=[],
    datas=[('TitanArmyControl/ta-logo-white.png', '.'), ('TitanArmyControl/ta-icon-black.png', '.')],
    hiddenimports=['pystray._win32', 'TitanArmyControl.windows_backend'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['TitanArmyControl.linux_backend', 'numpy'],
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
    name='TitanArmyControl',
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
    icon=['TitanArmyControl/ta-icon-black.png'],
)
