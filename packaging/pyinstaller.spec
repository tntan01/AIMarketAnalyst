# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["../main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("../assets", "assets"),
        ("../config/*.json", "config"),
        ("../prompts", "prompts"),
        ("../data/migrations/*.sql", "data/migrations"),
    ],
    hiddenimports=["PyQt6.QtWebEngineWidgets"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AI Market Analyst",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AI Market Analyst",
)
