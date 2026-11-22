# PyInstaller one-directory bundle; the fixture is the only application data.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata


root = Path(SPECPATH)
metadata = [entry for name in ("duckdb", "wrenai", "wren-core-py")
            for entry in copy_metadata(name)]
analysis = Analysis(
    [str(root / "runtime_check.py")],
    pathex=[str(root)],
    datas=[(str(root / "fixtures/receiving.sql"), "fixtures"), *metadata],
    hiddenimports=["wren.connector.duckdb", *collect_submodules("sqlglot.dialects")],
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive, analysis.scripts, [], exclude_binaries=True,
    name="nfldb-runtime-check", console=True, upx=False,
)
COLLECT(executable, analysis.binaries, analysis.datas,
        name="nfldb-runtime-check", upx=False)
