from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

project_root = Path(SPECPATH).parent
textual_data, textual_binaries, textual_hidden = collect_all("textual")
hidden_imports = [
    *textual_hidden,
    *collect_submodules("sqlalchemy.dialects.sqlite"),
    *collect_submodules("uvicorn"),
]

analysis = Analysis(
    [str(project_root / "packaging" / "soki_trade.py")],
    pathex=[
        str(project_root / "packages" / "shared" / "src"),
        str(project_root / "apps" / "api" / "src"),
        str(project_root / "apps" / "terminal-tui" / "src"),
    ],
    binaries=textual_binaries,
    datas=textual_data,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["celery", "psycopg"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="SokiTrade",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
