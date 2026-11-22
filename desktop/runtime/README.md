# Packaged analytics check

Builds a self-contained Python executable that queries a synthetic DuckDB fixture
through Wren. The fixture tests aggregation across unequal target counts and
handling of an invalid query.

## Build and check

Requires Python 3.12 and uv 0.11.23 on the target operating system.
From this directory:

```sh
uv sync --locked --group build
uv run --locked --group build python runtime_check.py
uv run --locked --group build pyinstaller runtime.spec --clean --noconfirm
uv run --locked --group build python verify_bundle.py dist/nfldb-runtime-check
```

The complete output folder is required, not just its executable. Windows uses
`nfldb-runtime-check.exe`; macOS uses `nfldb-runtime-check`.

The verifier copies the bundle into a path containing spaces and Unicode, clears
PATH, invalidates Python development paths and runs from a separate working
directory. It checks aggregate results, bundled dependency locations, unchanged
fixture bytes and the expected invalid-query exit. Each process must finish
within 60 seconds. Successful verification prints a JSON report including size
and dependency versions.

`runtime.spec` explicitly includes Wren's dynamically loaded DuckDB connector,
SQL dialect modules, package metadata and the SQL fixture. Dependencies use a
separate `uv.lock`; building this executable does not change the API environment.

The [runtime workflow](../../.github/workflows/desktop-runtime.yml) builds and
checks Windows x64, macOS arm64 and macOS x64. Native packages require separate
builds. These commands need no model credentials or production database.

Successful workflow runs attach a verified bundle archive for each platform.
Extract the complete folder before running the executable. These are unsigned
diagnostic builds, not application installers.
