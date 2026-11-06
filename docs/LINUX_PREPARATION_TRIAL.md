# Linux preparation trial

This trial checks the offline worker on Ubuntu 24.04 before cloud publication.
It uses a separate checkout, copied database and restored captures. It never
selects a release, replaces the serving database or deploys the website.

“Offline” means preparation happens before visitors make requests. Dependency
setup downloads packages, the passing exporter checks upstream play credits,
and refresh preparation observes upstream versions and downloads vendor feeds.
This is not an internet-disconnected replay.

## Environment

Use Linux-native storage for the checkout and generated files. Keep the Windows
checkout's `.venv` separate: Python environments and compiled R packages cannot
be copied between operating systems.

The tested runtime pins are Python 3.12, uv 0.11.23 and R 4.6.1. Restore R packages
from `api/r/renv.lock`; do not regenerate the lock or substitute newer packages.
Git must apply `.gitattributes`, including the lock's intentional CRLF bytes.

R can be installed using [Posit's versioned Ubuntu packages](https://docs.posit.co/resources/install-r.html).
The trial uses the Ubuntu 24.04 amd64 package for **4.6.1**, installed at
`/opt/R/4.6.1`. System prerequisites include `build-essential`, `gfortran`,
`pkg-config`, `libcurl4-openssl-dev`, `libssl-dev`, `libxml2-dev`, `libicu-dev`,
`libblas-dev` and `liblapack-dev`. These are operating-system dependencies;
the R lock records package versions, not a complete operating-system image.

From the separate checkout's `api/` directory, with uv 0.11.23 available:

```bash
uv sync --locked --python /usr/bin/python3 --python-preference only-system
export LC_ALL=C
export MAKEFLAGS=-j4
export OPENBLAS_NUM_THREADS=2
export OMP_NUM_THREADS=4
export RENV_CONFIG_CACHE_ENABLED=FALSE
rscript=/opt/R/4.6.1/bin/Rscript
library="$PWD/data/r-library"
"$rscript" --vanilla r/restore.R "$library"
"$rscript" --vanilla r/environment.R r/renv.lock "$library"
"$rscript" --vanilla r/test_environment.R "$library"
```

## Restore and check the input boundary

Transfer the capture ZIP and a closed source database as separate trial inputs.
Check their SHA256 values against the recorded source artifacts before and after
copying. Restore to a new directory; preserve every original manifest byte.

```bash
export NFL_TEST_MODE=1
export DUCKDB_MEMORY_LIMIT=8GB
export DUCKDB_THREADS=4
uv run --locked python -m jobs.captures restore \
  --archive data/inputs.zip --output data/restored > data/restored-paths.json
core=$(uv run --locked python -c 'import json; print(json.load(open("data/restored-paths.json"))["core"])')
passing=$(uv run --locked python -c 'import json; print(json.load(open("data/restored-paths.json"))["passing"])')
```

The archive reader validates the full inventory, payload hashes and restored
collection identities. Windows absolute paths inside immutable manifests are
resolved through the archive's directory map; editing those paths would change
the source identity.

Run the R provenance controls against a restored receiving run with an upstream
proof. Then run `jobs.passing_preview` using the Linux R executable and library.
Compare the resulting canonical rows to the same saved Windows calculation,
including all split dimensions, player keys, counts, metrics and missing values.
These are diagnostic exports; they do not replace the restored input pair.

```bash
receiving=$(uv run --locked python -c 'import sys; from pathlib import Path; from pipeline.receiving_core_collection import open_core_inputs; print(open_core_inputs(Path(sys.argv[1])).receiving_run(2026)[0])' "$core")
"$rscript" --vanilla r/test_upstream_inputs.R \
  "$receiving" data/r-provenance-controls "$rscript" "$library"
uv run --locked python -m jobs.passing_preview \
  --core-inputs "$core" --exports data/linux-passing-2026 --season 2026 \
  --rscript "$rscript" --r-library "$library"
```

## Prepare and validate

Use new candidate and release paths and a copy of previously acknowledged
watermarks. The command rebuilds analytics against the restored input pair,
validates the candidate, and validates again while creating the release bundle.

```bash
uv run --locked python -m jobs.refresh prepare data/previous-watermarks.json \
  --source data/source.duckdb --candidate data/linux-candidate.duckdb \
  --release data/linux-release --seasons 2026 \
  --core-inputs "$core" --passing-inputs "$passing"
uv run --locked python -m jobs.release verify --release data/linux-release
```

Measure dependency setup separately from preparation. Record elapsed time,
process memory and disk use, including restored captures, source, candidate,
release and temporary files. Sampled memory/disk peaks can miss brief spikes;
summed process RSS can count shared pages more than once. Choose worker capacity
with headroom rather than treating a measurement as a guaranteed upper bound.

Before calling the trial complete, confirm the source database, capture ZIP and
old watermarks are unchanged, both validation gates cover all stored seasons and
HTTP reads, the bundled database matches the candidate, and historical canonical
passing/receiving rows are unchanged. Cloud storage, publication selection and
deployment are separate steps.

## Verified result: October 29, 2026

The trial completed on Ubuntu 24.04 x86_64 under WSL2, using a clean checkout of
`e765b85`, Python 3.12.3, uv 0.11.23 and R 4.6.1. No application-code,
dependency-lock, statistical-definition or availability-policy changes were
needed. This is a local Linux proof; the GitHub-hosted workflow has not run yet.

- All 49 locked R packages restored, and the environment checks passed.
- 99 targeted Python checks and nine real R provenance controls passed.
- All 4,741 captured files restored with unchanged hashes and collection
  identities, including the native source-version proof.
- The Linux calculator regenerated all 17 passing views for the saved 2026
  inputs: all 1,831 canonical rows matched Windows exactly. Normalizing CRLF/LF
  makes the CSV bytes identical too.
- Candidate and release validation each passed receiving and passing checks for
  all 28 seasons, 1999–2026, historical checks and 102 HTTP reads.
- Bidirectional `EXCEPT ALL` found zero differences in historical passing and
  receiving split rows for 1999–2025. All five protected original databases,
  the input ZIP, previous watermarks and original release manifest stayed intact.
- The release database is byte-identical to the Linux candidate. No release was
  selected, uploaded or deployed.

| Measurement | Observed result |
| --- | --- |
| R package restore | 2 minutes 48 seconds |
| Capture restore | 19 seconds |
| All-view 2026 passing calculation and validation | 2 minutes 7 seconds |
| Full preparation, candidate gate and release gate | 26 minutes 26 seconds |
| Sampled peak summed process RSS during preparation | 1.46 GiB |
| Largest observed trial-directory size | 10.23 GiB |

Setup and diagnostic calculations ran before the measured preparation. Memory
and intermediate disk use were sampled every ten seconds; the final directory
size was also measured after release creation. The directory includes restored
inputs, ZIP, source/candidate/release databases, diagnostic exports, the checkout,
Python environment, isolated R library and local R setup downloads/cache. It
excludes OS packages, `/opt/R/4.6.1` and the external uv cache. These measurements
are not a total-machine peak or a promise about another runner's capacity.

Evidence is retained locally under ignored `api/data/linux-trial-evidence-20261029/`:
the independent proof, both validation reports, release manifest, resource report,
environment/package inventory, test XML and timing files. The complete Linux
artifacts remain in the isolated trial checkout. The validated candidate SHA256
is `8210111e23cb2f6f2200c4ee653f4b5e2bc567025ceca2430916ad7129da60e6`.

The next integration can use an explicit Ubuntu 24.04 worker. Check its actual
free disk and memory before restoring captures, allow for new capture/ZIP and
temporary-file growth, and keep deployment image building in a separate job.
GitHub documents different memory allocations for public and private standard
runners; this local trial does not establish their available disk headroom.
See [GitHub-hosted runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
