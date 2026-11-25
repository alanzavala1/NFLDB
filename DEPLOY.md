# Deployment

NFLDB runs at [nfl-db.cloud.run](https://nfl-db.cloud.run). React, FastAPI and a
validated DuckDB snapshot ship in one Docker image. R runs only in data preparation.

## Deploy a release

Run **Deploy native snapshot** in GitHub Actions
(`.github/workflows/deploy-native.yml`) with:

| Input | Value |
|---|---|
| `target` | `preview` or `production` |
| `operation` | `deploy` |
| `pointer` | Cloud selection URI |
| `pointer_generation` | Exact generation from `jobs.publish current` |
| `pointer_sha256` | Exact selection hash from that receipt |

The workflow downloads and verifies the selected bundle, builds the image, runs
API/reconciliation/read-only checks inside it, and deploys its immutable image
digest. It checks the candidate and rechecks the selection before moving traffic.
Post-promotion checks verify the public service. A receipt records the previous
revision, image identity and traffic state.

Preview uses `nfldb-native-preview`; production uses `nfldb`, both in
`us-central1`. The workflow configures 4 GiB RAM, 2 CPUs and zero minimum instances;
maximum instances are one and three respectively. DuckDB is capped at 2,400 MB
and two threads. Each instance reads its own copy of the database.

For automatic deployment after data refresh, configure
[refresh automation](docs/NATIVE_REFRESH_AUTOMATION.md).

## Rollback

Run the same workflow with operation `rollback`, the matching target and the
previous verified `revision` from a deployment receipt. Rollback restores that
revision's code and baked database together, without rebuilding either.

An unhealthy candidate is not promoted. If post-promotion checks fail, the script
attempts to restore the previous revision and saves failure evidence. A first
preview creation has no prior revision. If recovery fails, inspect `before.json`
and restore the recorded traffic allocation.

Deployment and rollback share a non-cancelling queue per target. Cloud selection
and traffic updates are separate operations: rollback does not change the desired
data selection, and independent console/CLI changes are not serialized by GitHub.
Keep the previous revision and image available for recovery.

## Local image check

After [downloading a release](docs/CLOUD_RELEASES.md), run these Bash commands from
the repository root. Set `RELEASE` to its `release/` directory:

```sh
docker build --target native --provenance=false \
  --build-context native_snapshot="$RELEASE" -t nfldb:check .
docker run --rm --read-only --tmpfs /tmp --memory 4g --cpus 2 \
  nfldb:check python -m jobs.deploy check-image
docker run --rm --read-only --tmpfs /tmp -p 8080:8080 nfldb:check
```

Both Docker targets require an explicit data context. The `legacy` target accepts
`legacy_snapshot` for examining older databases; production rollback normally
uses an existing Cloud Run revision. The source build context excludes local
data, credentials and private planning files.

## Cloud setup

The project needs Cloud Run, Artifact Registry, Cloud Storage and IAM Credentials,
an Artifact Registry repository named `nfldb` in `us-central1`, and a publication
bucket. Workflows use Workload Identity Federation with these repository secrets:

| Secret | Purpose |
|---|---|
| `GCP_PROJECT_ID` | Google Cloud project |
| `GCP_WIF_PROVIDER` | GitHub OIDC provider resource |
| `GCP_SA_EMAIL` | Workflow service account |

The deployer needs Cloud Run administration, registry write, bucket read and
permission to act as the runtime service account. Publication also needs object
write permissions. Restrict the identity provider to the intended repository;
see [Google's authentication action](https://github.com/google-github-actions/auth).

The public hostname maps to the production service and follows its traffic
allocation. Deployment status and revision identities come from workflow receipts
and Cloud Run, rather than fixed values in this guide.
