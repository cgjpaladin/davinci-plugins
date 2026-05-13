# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('renamer_web.html', '.'), ('../shared', 'shared')]
datas += collect_data_files('webview')
datas += collect_data_files('bottle')


a = Analysis(
    ['renamer_web.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['webview', 'webview.platforms.cocoa', 'bottle', 'proxy_tools', 'pyobjc'],
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
    name='批量命名工具',
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
    name='批量命名工具',
)
app = BUNDLE(
    coll,
    name='批量命名工具.app',
    icon='app_icon.icns',
    bundle_identifier=None,
)
