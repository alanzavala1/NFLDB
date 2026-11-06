# Deploying NFLDB

The React frontend and FastAPI API ship in one container with an offline-prepared
DuckDB snapshot. Cloud Run serves that snapshot **read-only**. It never downloads
sources, prepares analytics, or updates watermarks during a visitor's request.
R runs in the offline worker, not the serving container.

## Native deployment

- `deploy-native.yml` supports **preview** (`nfldb-native-preview`) and
  **production** (`nfldb`). Both consume an exact, verified cloud selection.
- The [native refresh workflow](docs/NATIVE_REFRESH_AUTOMATION.md) connects
  capture, calculation, validation and publication. Set `NATIVE_REFRESH_POINTER`
  to the desired selection URI and `NATIVE_REFRESH_TARGET` to `production` to
  deploy each successfully prepared release through the same deployment gate.
- The legacy `refresh.yml` and `deploy.yml` workflows are retired by this change.
  Disable their existing GitHub registrations and finish any in-flight legacy
  jobs before the first native production switch.
- Validation describes the captured inputs. Later upstream versions are picked
  up by subsequent refreshes.

See [cloud publication and selection](docs/CLOUD_RELEASES.md) and
[offline preparation](docs/OFFLINE_RELEASES.md) for the preceding steps.

## Native workflow

Run **Deploy native snapshot** in GitHub Actions with operation `deploy` and
target `preview` or `production`.
Supply the selection URI, exact object generation, and SHA256 returned by
`jobs.publish current`. Retrying a failed deployment does not require new data;
deployment success is separate from preparation success.

The workflow:

1. Downloads the selected bundle and verifies its hashes, native validation
   report, and compatibility with the checked-out analytics/API policy.
2. Builds the frontend and locked Python environment. Only the four native
   release files enter through the separate `native_snapshot` build context.
3. Runs the certified API requests, including real startup and read-only checks,
   then reconciliation and assistant compatibility tests inside the image.
   Missing data fails the native gate rather than silently skipping.
4. Pushes an image tagged with code/data/run identities, resolves its immutable
   registry digest, and deploys **that digest** to the selected service.
5. Checks the candidate's image identity, readiness, API health, seasons response,
   and frontend before promoting it. It rechecks the latest selection immediately
   before promotion; a superseded job stops.
6. Verifies the service after promotion and saves the previous revision, exact
   image, traffic state, and download receipt as a workflow artifact.

Deployments and rollbacks share a GitHub concurrency group and never cancel a
running traffic operation. This serializes this workflow, not independent console
or CLI changes. Selection and Cloud Run traffic are separate services, so their
updates are not one atomic transaction. A selection changed after the final
check requires a subsequent deploy.

Both services use 4 GiB RAM, 2 CPUs and zero minimum instances. Preview allows
one maximum instance and production allows three.
DuckDB is capped at 2,400 MB and two threads. Read-only serving supports multiple
replicas; the preview's single-instance cap is a cost/testing choice.

### Local image check

After `jobs.publish download` completes into a new directory:

```bash
# From the repository root; RELEASE is the download's release/ directory.
docker build --target native --provenance=false \
  --build-context native_snapshot="$RELEASE" -t nfldb-native:check .
docker run --rm --read-only --tmpfs /tmp --memory 4g --cpus 2 \
  nfldb-native:check python -m jobs.deploy check-image
docker run --rm --read-only --tmpfs /tmp -p 8080:8080 nfldb-native:check
```

The shared source context excludes local databases, captures, virtual environments,
credentials, and private planning documents. The native image has no legacy
database copy. Both Docker targets require an explicit data context; a bare
`docker build .` is intentionally insufficient.

## Rollback

Run the same workflow with operation `rollback`, the matching target, and the
full **previous revision** from a successful deployment artifact.
The script verifies that the revision belongs to the selected service, checks its tagged
URL, then sends 100% of traffic to it. This restores the previous code **and baked
database together**, without rebuilding either.

An unhealthy candidate is not promoted. If checks fail after a traffic switch,
the script attempts to restore the exact previous revision and saves failure
evidence. If restoration fails, the job reports it; use `before.json` to recover.
The first preview creation has no previous revision to restore. Rollback does
not edit the desired cloud selection; resolve the cause before retrying it.

The production service must already have a revision available for rollback.
Cloud Run documents the underlying command in its
[rollback guide](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration):

```bash
gcloud run services update-traffic nfldb-native-preview --region us-central1 \
  --to-revisions=EXACT_PREVIOUS_REVISION=100
```

## Existing cloud setup

Workflows use Workload Identity Federation: GitHub exchanges a short-lived OIDC
token for Google credentials, with no downloadable service-account key. The
project needs Cloud Run, Artifact Registry, Cloud Storage, and IAM Credentials
enabled, an Artifact Registry Docker repository named `nfldb` in `us-central1`,
and the publication bucket.

| Repository secret | Purpose |
| --- | --- |
| `GCP_PROJECT_ID` | Google Cloud project |
| `GCP_WIF_PROVIDER` | Existing GitHub OIDC provider resource |
| `GCP_SA_EMAIL` | Deployment service account |

The deployer needs Cloud Run administration, Artifact Registry write, bucket
object read, and permission to act as the runtime service account. Publication
and selection writers also need object write permissions. Restrict the WIF
provider to the intended repository. Google's
[authentication action](https://github.com/google-github-actions/auth)
documents one-time setup.

## Legacy rollback image

The Dockerfile retains an explicit legacy build target for examining older
snapshots. A local directory containing `nfl.duckdb` supplies `legacy_snapshot`:

```bash
docker build --target legacy --provenance=false \
  --build-context legacy_snapshot="$LEGACY_DIRECTORY" -t nfldb-legacy:check .
```

Production rollback uses the previous Cloud Run revision, which already contains
its code and data. Keep that revision and its image available through cutover.
