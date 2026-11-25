# Scheduled data refresh

The **Prepare native data release** workflow builds new data separately from the
serving website. It is defined in `.github/workflows/refresh-native.yml` and
scheduled for 09:00 UTC daily; GitHub scheduling can be delayed.

## Configuration

| Repository setting | Purpose |
|---|---|
| Variable `NATIVE_REFRESH_POINTER` | Existing cloud selection URI; required for scheduled runs |
| Variable `NATIVE_REFRESH_TARGET` | `preview` or `production` to deploy a successful selection |
| Secrets `GCP_PROJECT_ID`, `GCP_WIF_PROVIDER`, `GCP_SA_EMAIL` | Google Cloud authentication through GitHub OIDC |

Manual runs accept a `pointer` override, optional `season` and `force` flag.
Without a season, planning uses the newest scheduled year. `force` bypasses the
unchanged-source shortcut, not validation. The native path requires that season's
three RDS assets; it does not handle schedules-only preseason refreshes.

The worker uses Ubuntu 24.04, Python 3.12, uv 0.11.23 and R 4.6.1. Python and R
locks are verified even when dependency caches are restored. Cloud permissions
must allow release creation and conditional selection updates; see
[deployment setup](../DEPLOY.md#cloud-setup).

## Run sequence

1. Read the selected publication and compare its watermarks with three native
   RDS feeds and nine watched vendor feeds. No large data download is needed yet.
2. Stop if unchanged. Otherwise download the pinned database/captures and restore
   the historical input collections.
3. Capture the refreshed season, calculate passing exports, and combine them with
   unchanged history. Historical R exports are reused.
4. Prepare a candidate, validate it during release packaging and pack matching captures.
5. Publish to a new immutable prefix and conditionally select it using the pointer
   generation observed before preparation.
6. If configured, invoke **Deploy native snapshot** with that exact selection.

Refresh jobs share one queue. A concurrent external selection change still causes
the conditional update to fail. Failed preparation does not publish or acknowledge
new source versions. Failed deployment retains the completed publication for retry.

## Local operation

From `api/`, using an authenticated Google Cloud CLI and the
[locked R environment](../api/r/README.md):

```sh
uv run --locked python -m jobs.refresh_native plan \
  --pointer gs://BUCKET/native/candidates/current.json \
  --season 2026 --output data/plan.json
```

When `changed` is true, [download](CLOUD_RELEASES.md#download-a-selected-release)
with `--include-captures` and the plan's `selection.pointer_generation` and
`selection.pointer_sha256`. Then:

```sh
uv run --locked python -m jobs.refresh_native prepare \
  --plan data/plan.json --download data/selected-download \
  --workspace data/new-refresh --rscript PATH_TO_RSCRIPT \
  --r-library PATH_TO_LOCKED_LIBRARY
```

Use new output paths. `refresh.json` marks completed preparation; publication and
selection remain explicit [cloud release commands](CLOUD_RELEASES.md).

## Diagnosis and recovery

Workflow artifacts retain plans, logs, validation reports and publication/selection
receipts. Large databases and captures remain in Cloud Storage. `[refresh-timing]`
records in `preparation.log` report stage duration and failure status; nested
stage times overlap and must not be summed.

Optional failed or mid-build changed sources retain their old watermarks for a
later retry. A completed but unselected release can be inspected or selected
explicitly. Retry a failed deployment with its saved selection identity rather
than rerunning calculation. See [rollout and rollback](../DEPLOY.md).
