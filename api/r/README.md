# Offline receiving R environment

R runs the official nflfastR calculator during data preparation. The website
continues to serve requests with Python; no R install is needed in the serving
image. This directory owns the dependency setup for the existing preview job.

`renv.lock` records R **4.6.1** and **49** packages, including recursive imports
and five recommended packages supplied by our R installation. `renv` **1.3.1**
restores exact versions, with no fallback to newer versions. `.R-version` is
the runtime pin; setup checks that it agrees with the lock.

## Setup and build

Install [R 4.6.1](https://cran.r-project.org/); pass its `Rscript` executable
explicitly if it is not on PATH. From `api/`, in PowerShell:

```powershell
# Replace this executable path with your R 4.6.1 installation.
$rscript = 'data/upstream-r-trial/R-4.6.1/bin/Rscript.exe'
$library = 'data/receiving-r-library'
$env:LC_ALL = 'C'
& $rscript --vanilla r/restore.R $library
if ($LASTEXITCODE -ne 0) { throw 'R setup failed' }
& $rscript --vanilla r/environment.R r/renv.lock $library
if ($LASTEXITCODE -ne 0) { throw 'R dependency check failed' }
& $rscript --vanilla r/test_environment.R $library
if ($LASTEXITCODE -ne 0) { throw 'R environment tests failed' }

uv sync --locked
uv run --locked python -m jobs.receiving_preview `
  --source data/nfl.duckdb --candidate data/receiving-preview-example.duckdb `
  --exports data/receiving-preview-example-exports --seasons 2009 `
  --rscript $rscript --r-library $library
```

In another shell, the same scripts accept ordinary positional paths:
`Rscript --vanilla r/restore.R data/receiving-r-library`. The command above
demonstrates a receiving preview; the integrated candidate/release path is
documented in [offline releases](../../docs/OFFLINE_RELEASES.md).
Source must be closed without a WAL; candidate and export paths must be new.
Keep installations, packages, caches and generated data under ignored `data/`.
Setup installs packages only in the explicit library; it does not install R,
change PATH, write a global `.Rprofile`, or delete unrelated packages.

The job freezes the producer, dependency check and lock before checking the
environment or downloading inputs. It excludes user/site libraries, checks all
locked versions and recursive imports, and loads compiled dependencies. Missing
or incompatible packages stop the build and leave `R-environment.log` for
diagnosis. The export manifest binds the frozen lock and check script and records
the verified versions; the Python worker verifies those artifacts again.

## Verification and limits

On October 23, 2026, setup was restored into a new Windows x64 library with
`RENV_CONFIG_CACHE_ENABLED=FALSE`, then exercised by the real 2009 preview build
across all 17 receiving views. The environment tests also reject an incorrect R
version, a changed transitive package, an incomplete lock and an empty library.
These checks need no NFL feeds after setup; the actual build downloads NFL data.
All 17 views produced exactly the same 2009 rows as the previously audited v13
candidate. All 81 manifest-bound files verified; the source and canonical split
rows were unchanged, and the full snapshot gate still rejected the preview.
Running setup a second time found the library already synchronized.
Backend validation: **1,028 passed, 2 skipped**. Ignored evidence is under
`api/data/upstream-r-trial/`: `renv-clean-restore.log`, `renv-preview-build.log`,
`renv-preview-verification.json` and `renv-backend-tests.xml`.

On October 29, 2026, a fresh Ubuntu 24.04 library restored all 49 locked packages
under R 4.6.1 and passed the environment checks and nine real provenance controls.
The Linux passing calculator rebuilt all 17 views for the saved 2026 inputs;
all 1,831 canonical rows matched the Windows values exactly. See the
[Linux preparation trial](../../docs/LINUX_PREPARATION_TRIAL.md) for the worker
setup and separate database-validation checks. CSV byte hashes differ because
of line endings; the comparison uses parsed rows and exact values.

R is a prerequisite, not downloaded automatically. macOS restoration has not
been executed here. Linux/macOS may need system libraries and a compiler for
packages such as curl, stringi and xgboost; renv locks R packages, not operating
system packages. Even Windows may need Rtools if a pinned binary is no longer
available and CRAN must build an older source package. Package repositories must
still provide the pinned artifacts. This is dependency reproducibility, not a
claim of permanent artifact archival or bit-identical cross-platform binaries.

NFL feeds can change independently of packages. The preview retains hashes and
copies of consumed inputs, but this setup does not turn it into a fully frozen
offline replay, validate every season, or make the preview publishable. The
preview now qualifies players from the same bound fresh play context used in the
calculation, preserving the existing rule. The copied database's other analytics
still need the main fresh-source build integration.

## Deliberate dependency updates

Evaluate upgrades in a separate ignored library. With the desired packages and
`renv` installed there, use `renv::snapshot(project="r", library=LIBRARIES,
packages=c("nflfastR", "nflreadr", "jsonlite", "digest", "renv"),
lockfile="r/renv.lock", prompt=FALSE)` from `api/`. `LIBRARIES` must include the
isolated library and the R base/recommended library. Review the generated diff,
update `.R-version` or the pinned bootstrap version in `restore.R` if applicable,
restore into a fresh library, run the checks, and revalidate real receiving
outputs before accepting an upgrade. Do not regenerate the lock during builds.

Reference: [renv snapshot](https://rstudio.github.io/renv/reference/snapshot.html)
and [restore](https://rstudio.github.io/renv/reference/restore.html).
