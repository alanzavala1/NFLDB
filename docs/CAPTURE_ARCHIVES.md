# Portable native captures

Native receiving/core and passing captures can be packed together and restored
into a different workspace. This uses Python's standard ZIP support, including
ZIP64 for the full historical dataset; no new dependency or R runtime is needed.

From `api/`, using new output paths with existing parent directories:

```powershell
uv run --locked python -m jobs.captures pack `
  --core-inputs PATH_TO_CORE_COLLECTION `
  --passing-inputs PATH_TO_PASSING_COLLECTION `
  --output data/captures.zip

uv run --locked python -m jobs.captures restore `
  --archive data/captures.zip --output data/restored-captures
```

Restore prints the `core` and `passing` directories to pass to `jobs.refresh
prepare`, `jobs.validate` or `jobs.release build`. Keep the entire restored root
together, including its `capture-map.json`; moving an individual child directory
loses the relocation context.

## What is preserved

Packing follows the collection indexes to converted core inputs, receiving source
runs and passing exports. It includes each original `run.json` and its declared,
hash-bound files. Unlisted logs and diagnostic outputs are excluded. The native
manifests and source data are copied byte-for-byte, preserving source revisions
and their relationship to prepared database metadata.

A separate map associates original directory strings with directories inside
the restored root. This supports Windows path strings in a Linux workspace
without rewriting the hashed manifests. When a relocation map is present,
unmapped references fail rather than falling back to original machine paths.
Ordinary unarchived captures retain their existing absolute-path behavior.

## Integrity and failure handling

Packing verifies declared source hashes and writes a new archive exclusively.
Restoring requires an absent destination, an exact file inventory, matching
sizes and hashes, safe relative paths and regular file entries. Duplicate,
undeclared, missing, symlink and escaping archive members are rejected. Restore
writes files explicitly rather than using unrestricted archive extraction.
Failure removes only the files and directories created by that restore.

Restored native readers retain their original checks. Archive integrity is not
a substitute for native statistical/source validation before release, and the
archive is not an authenticated publisher signature. It must come from the
project's controlled artifact storage.

## Scope

This makes existing captures reusable by cloud workers. It does not fetch new
upstream files, rerun calculators, record new watermarks, publish a database or
change the scheduled workflow. Fresh capture/version binding and cloud release
selection remain separate steps in [the release workflow](OFFLINE_RELEASES.md).

## Checkout consistency

The repository pins line endings for calculator scripts and the R dependency
lock in `.gitattributes`. The lock retains its existing CRLF representation on
every platform, and R scripts use LF. These files have byte-level policy hashes;
automatic Git conversion must not make identical dependencies appear changed.

## Local proof (October 28, 2026)

The complete 28-season input set contains 4,734 declared files totaling
6,218,596,029 bytes. Its compressed archive is 1,134,590,182 bytes. Packing and
restoring preserve both collection revisions exactly.

Full native receiving and passing validation for 1999–2026, historical snapshot
checks and 102 HTTP reads passed using the restored inputs. The newly validated
release database matches the source candidate byte-for-byte. All five protected
working/proof databases remain unchanged, with no pending WALs.

The related test suites have 101 distinct passing checks. Tests cover restored
feeds with original directories unavailable, repacking, foreign path strings,
corruption, unsafe members, existing destinations and failure cleanup. Checkout
copies made with `core.autocrlf=false` and `core.eol=lf` also match the captured
R producer, converter, environment and lock hashes under the pinned attributes.
The full data proof ran on Windows; running the workflow on Linux remains part
of cloud integration. Proof logs and artifacts remain ignored under `api/data/`.
