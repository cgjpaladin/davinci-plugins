# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['renamer_v02.py'],
    pathex=[],
    binaries=[],
    datas=[('_build/table_v02.html', '.')],
    hiddenimports=['webview', 'bottle'],
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
    name='批量命名工具-v4.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app_icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='批量命名工具-v4.0',
)
app = BUNDLE(
    coll,
    name='批量命名工具-v4.0.app',
    icon='app_icon.icns',
    bundle_identifier=None,
)
