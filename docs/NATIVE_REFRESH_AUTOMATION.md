# Native refresh automation

This job prepares data before visitors request it. The serving container keeps
reading its existing snapshot while a separate worker builds the next release.
Publication and deployment are separate: selecting new data does not replace a
running Cloud Run container.

As of the November 6 cutover, both native workflows are active on `main`,
`NATIVE_REFRESH_POINTER` selects the production pointer and
`NATIVE_REFRESH_TARGET=production` enables deployment after successful preparation.
The first hosted preparation/publication succeeded. Its deployment handoff
exposed GitHub's suppression of a secret-derived URI output, fixed in `8ecae7f`.
The validated release subsequently passed the independent preview and production
deployment workflows. The corrected combined handoff awaits the next changed-source
run. See [the cutover evidence](../DEPLOY.md#verified-production-cutover--november-6-2026)
for exact runs, the live revision and rollback target. The November 1 trial below
records the earlier local checkpoint.

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
Configure a trial/candidate selection while proving automation. Set repository
variable `NATIVE_REFRESH_TARGET` to `preview` or `production` to pass a successful
selection to the reusable `deploy-native.yml` workflow. The deployment pins the
exact selection identity emitted by this refresh and rechecks it before traffic
promotion. An unchanged-source run skips preparation and deployment. A failed
deployment retains its publication for a manual retry through **Deploy native
snapshot**. See [DEPLOY.md](../DEPLOY.md) for rollout and rollback.

The job records plan, preparation logs, validation reports, publication receipt,
and selection receipt as a GitHub artifact. Large databases and captures live
in the versioned cloud publication rather than duplicated workflow artifacts.
The legacy refresh/deploy workflows are retired by the native cutover change.
Preparation and publication use the versioned native objects and selection.

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

## Verified preparation trial — November 1, 2026

The ordinary plan and preparation commands completed using the existing
authenticated cloud SDK and pinned Linux worker. The base was the previously
verified cloud download, rechecked by the orchestrator before and after use.
This trial reused that download and existing R library; it did not repeat their
setup or transfer. The GitHub workflow passed actionlint but has not been pushed,
dispatched, or enabled through `NATIVE_REFRESH_POINTER`.

- The metadata plan detected updates to all 12 watched feeds.
- Fresh 2026 inputs contained 20,841 play rows and 8,295 weekly-stat rows,
  compared with the base snapshot's 18,738 and 7,447.
- Native receiving capture and every passing view completed. The combined input
  collections retained all 28 seasons, 1999–2026.
- Candidate and release validation both passed, including 102 API requests.
- Bidirectional `EXCEPT ALL` found no changes to 1999–2025 passing/receiving
  split rows. Historical capture identities, all five protected databases, the
  downloaded base, original release and original archive retained their hashes.
- The candidate and release database hashes matched, and all three native
  source-version acknowledgments matched the fresh proof. The new capture ZIP
  contained 4,741 manifest-bound files and matched the release's input revisions.

Preparation took approximately 52 minutes 39 seconds, measured from the job
log's creation and last-write timestamps. The completed workspace used 9.0 GiB;
that excludes the separately stored base download, installed runtimes, package
libraries and caches. This is a local Linux measurement, not a GitHub-hosted
runner benchmark or a measured peak for the whole machine.

The analytics/API policy remains
`f72611443cf21bba4fc9ecec485459304b10e6094c4997339747b4ac16ef7ef4`.
No statistical definitions, tolerances, availability rules, or dependency locks
changed. The related 67 Python controls passed on both Windows and Linux.
Evidence stays ignored under `api/data/native-automation-*20261101*`.

The same release and capture ZIP were then uploaded and remotely verified at:

```text
gs://project-60bdbe3e-823a-46fb-b02-nfldb-data/native/releases/20261101-automation-12680c768522
publication.json generation: 1793598080995895
publication SHA256: e2ee4d5015a799504dfc268375490c83a3c7376c3910fbae4a098bf8498ebf9a
```

The database is 1,060,384,768 bytes, SHA256
`d7711eb9941fa6e4b5ab78b67f44146f6198d1b6542fcd69d2810fa39111a8f0`.
The matching ZIP is 1,143,638,412 bytes, SHA256
`dc78cffeefe90a1d25860d0c8aeb8e2ef2e5aa9367a58296ab0124479cf721ee`.
The local Windows SDK read the finished Linux files through their WSL share;
upload and remote verification took approximately 19 minutes 27 seconds on this
connection. The hosted workflow uses Linux-native paths and still needs its own
runtime/network measurement.

Conditional selection succeeded using the original generation observed before
preparation. The existing trial pointer became generation `1793598229937426`,
SHA256 `f1c29caca7148c6e63fe881b66bfc481bbb74475764a9e0983034a5c8d4b317c`.
Production remained on `nfldb-00072-vs6` at 100% traffic; no image was built or
deployed in this chunk, and no legacy root object was written.

A subsequent ordinary plan read the new selection and detected seven later
upstream versions: the three native RDS feeds and four PFR feeds. Those updates
arrived after the versions used by this release; the next refresh remains
indicated. No repeated rebuild was started. The unchanged-source branch was
covered by the control tests, rather than falsely reporting this real post-run
check as unchanged. This is a versioned batch snapshot, not a live-feed mirror.
