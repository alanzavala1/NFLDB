# R calculator environment

The offline worker uses R to run the pinned nflfastR calculator. Serving the
prepared database requires only Python.

`.R-version` pins R 4.6.1. `renv.lock` records package versions, including
nflfastR, nflreadr and recursive imports; `restore.R` pins the renv bootstrap.
Builds verify these pins rather than updating them.

## Setup

Install the pinned R version and make its `Rscript` executable available. From
`api/`, restore an isolated library and run the environment checks:

```sh
Rscript --vanilla r/restore.R data/r-library
Rscript --vanilla r/environment.R r/renv.lock data/r-library
Rscript --vanilla r/test_environment.R data/r-library
```

Stop if a command fails. If Rscript is not on PATH, use its full path. In
PowerShell, invoke a quoted executable with `&`, for example:

```powershell
& 'C:/Program Files/R/R-4.6.1/bin/Rscript.exe' --vanilla r/restore.R data/r-library
```

The library path must be explicit. Setup does not install R or modify global
profiles or PATH. Keep libraries, caches and generated data under ignored `data/`.
Use the resulting executable/library paths as `--rscript` and `--r-library` in
[capture](../../docs/UPSTREAM_PROVENANCE.md) or [refresh](../../docs/NATIVE_REFRESH_AUTOMATION.md).

Ubuntu workers use the versioned R installation under `/opt/R/4.6.1`. System
requirements include compilers, gfortran, pkg-config, curl/OpenSSL, XML, ICU,
BLAS and LAPACK development libraries. See `.github/workflows/refresh-native.yml`
for the worker's installation steps. Windows source builds may need Rtools.
The lock covers R packages, not operating-system packages or permanent upstream
artifact availability.

## Reproducibility

Use separate native libraries on Windows and Linux; do not copy compiled packages
or virtual environments across operating systems. Preserve `.gitattributes`:
calculator scripts use LF, while the R lock retains its pinned CRLF bytes.

Exports bind calculator code, the lock, environment checks, inputs and output
hashes. Missing/incompatible packages stop calculation. Dependency caches do not
replace these checks. Cross-platform comparisons use canonical parsed rows;
CSV byte hashes can differ with line endings.

## Updating dependencies

Test upgrades in a separate library. Regenerate the lock deliberately using
`renv::snapshot`, review it with `.R-version` and the bootstrap pin, restore into
a clean library, then run environment and real calculator validation. Do not
regenerate the lock as part of an ordinary build.

See the renv [snapshot](https://rstudio.github.io/renv/reference/snapshot.html) and
[restore](https://rstudio.github.io/renv/reference/restore.html) references.
