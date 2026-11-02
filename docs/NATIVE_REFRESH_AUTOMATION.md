# Native refresh automation

This job prepares data before visitors request it. The serving container keeps
reading its existing snapshot while a separate worker builds the next release.
Publication and deployment are separate: selecting new data does not replace a
running Cloud Run container.

## What the worker does

1. Reads the current native selection and verifies its publication metadata.
   It compares the bundled watermarks with the three native RDS feeds and nine
   watched vendor feeds. This check does not download a database or capture ZIP.
2. If something changed, downloads that exact selected database and its matching
   capture archive. A forced run can rebuild when the watched versions match.
3. Restores the saved historical captures, captures the requested season, runs
   every passing view, and combines the fresh season with unchanged history.
4. Prepares a separate candidate and validates all stored seasons and API views.
   Existing statistical definitions, missing-data rules and validation gates
   remain in force. The R calculator is not rerun for unchanged historical years.
5. Packages the matching captures and writes `refresh.json` only after the new
   release, archive, historical coverage and original input hashes pass.
6. Publishes to a new immutable cloud prefix, then updates the configured
   selection using the generation observed **before** preparation started.

If another job selects a release first, the conditional update fails. It never
silently rereads the pointer and overwrites the newer selection. A completed but
unselected publication can remain available for inspection or explicit recovery.

## GitHub Actions

The workflow is `.github/workflows/refresh-native.yml`, named **Prepare native
data release**. It uses Ubuntu 24.04, locked Python dependencies, R 4.6.1, and the
existing `renv.lock`. The R installer has a pinned SHA256. The isolated R library
is cached, then verified on every run; the cache does not replace lock checks.
Runtime installation follows [Posit's versioned installation instructions](https://docs.posit.co/resources/install-r.html).

Scheduled runs are skipped until the repository variable
**`NATIVE_REFRESH_POINTER`** names an existing native selection JSON URI. For
manual runs, supply a `pointer` input or use that variable. Optional `season`
selects one year; blank uses the newest scheduled year. `force` bypasses the
source-change decision, not validation. Native capture currently requires the
season's three RDS assets to exist; preseason schedules-only refresh remains
outside this native path.

Use the same cloud authentication secrets as the deployment workflow. This job
also needs permission to create publication objects and conditionally replace
the selection. It renews authentication after preparation, before publication.
Configure a trial/candidate selection while proving automation. Switching the
live service requires the separate deployment and cutover work in
[DEPLOY.md](../DEPLOY.md).

The job records plan, preparation logs, validation reports, publication receipt,
and selection receipt as a GitHub artifact. Large databases and captures live
in the versioned cloud publication rather than duplicated workflow artifacts.
The existing legacy refresh workflow retains its own source and live deploy path
until cutover; this native job never overwrites its root database or watermarks.

## Local commands

From `api/`, using its locked Python environment:

```bash
python -m jobs.refresh_native plan --pointer gs://BUCKET/native/candidates/current.json \
  --season 2026 --output NEW_PLAN.json
```

If `changed` is true, use `jobs.publish download --include-captures` with the
plan's exact `selection.pointer_generation` and `selection.pointer_sha256`, as
described in [cloud releases](CLOUD_RELEASES.md). Then:

```bash
python -m jobs.refresh_native prepare --plan NEW_PLAN.json \
  --download VERIFIED_DOWNLOAD_DIRECTORY --workspace NEW_WORKSPACE \
  --rscript PATH_TO_RSCRIPT --r-library PATH_TO_LOCKED_LIBRARY
```

The command calls the existing capture, passing, composition, preparation and
archive jobs in fresh processes. It preserves the downloaded source and requires
a new workspace. Failed stages keep diagnostics and issue no completion marker;
they do not publish or advance watermarks. The ordinary `jobs.publish upload`
and `select` commands remain independently usable for publication recovery.

Watermarks acknowledge stable, successfully consumed versions. A source that
changes during preparation or fails an optional download retains its old mark,
so the next check can retry it. Publication describes captured inputs; it does
not guarantee that no upstream feed changed after the run.
