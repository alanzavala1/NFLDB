# Deploying NFLDB

The whole app ships as **one container**: a multi-stage [`Dockerfile`](./Dockerfile)
builds the React frontend, then a single Python process serves the static site,
the FastAPI API (under `/api`), and the baked-in 400MB DuckDB file. It targets
**Google Cloud Run** (free tier, scales to zero) but runs on any container host.

Because DuckDB is single-writer, run **one instance** (`--max-instances 1`).

---

## Path A — fastest (build & deploy from your machine)

Prereqs: Docker running, `gcloud` installed and logged in, a GCP project.

```bash
# one-time: enable APIs + create an Artifact Registry repo
gcloud services enable run.googleapis.com artifactregistry.googleapis.com
gcloud artifacts repositories create nfldb --repository-format=docker --location=us-central1

REGION=us-central1
IMAGE=$REGION-docker.pkg.dev/$(gcloud config get-value project)/nfldb/nfldb:latest

# build (bakes api/data/nfl.duckdb) and push
gcloud auth configure-docker $REGION-docker.pkg.dev --quiet
docker build -t "$IMAGE" .
docker push "$IMAGE"

# deploy — public, 1 instance, 1GB RAM
gcloud run deploy nfldb --image "$IMAGE" --region $REGION \
  --allow-unauthenticated --memory 1Gi --cpu 1 --max-instances 1 --port 8080
```

`gcloud run deploy` prints the public URL. Share it with friends.

> Even simpler: `gcloud run deploy nfldb --source . ...` lets Cloud Build build
> the image for you (no local Docker needed), as long as the DB is in `api/data/`.

---

## Path B — CI/CD (auto build + test + deploy via GitHub Actions)

[`.github/workflows/deploy.yml`](./.github/workflows/deploy.yml) pulls the DB
from a GCS bucket, builds the image, **runs the data-reconciliation tests
inside the image** (a release is blocked if the data doesn't reconcile with
official stats), pushes to Artifact Registry, and deploys to Cloud Run.

**One-time setup:**

```bash
PROJECT=$(gcloud config get-value project)
REGION=us-central1

gcloud services enable run.googleapis.com artifactregistry.googleapis.com storage.googleapis.com
gcloud artifacts repositories create nfldb --repository-format=docker --location=$REGION

# host the DB in a bucket (too big for git)
gcloud storage buckets create gs://$PROJECT-nfldb-data
gcloud storage cp api/data/nfl.duckdb gs://$PROJECT-nfldb-data/nfl.duckdb

# a deploy service account
gcloud iam service-accounts create nfldb-deployer
SA=nfldb-deployer@$PROJECT.iam.gserviceaccount.com
for role in run.admin artifactregistry.writer storage.objectViewer iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$SA --role=roles/$role
done
gcloud iam service-accounts keys create key.json --iam-account=$SA   # <- add to GitHub secret, then delete
```

**Add these GitHub repository secrets** (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `GCP_PROJECT_ID` | your project id |
| `GCP_SA_KEY` | the contents of `key.json` |
| `GCP_DB_BUCKET` | `<project>-nfldb-data` |

Then run the **Deploy to Cloud Run** workflow (Actions tab → Run workflow).
Flip the trigger in `deploy.yml` to `push: {branches: [main]}` for continuous
deployment once you trust it. (Hardening: swap the SA key for Workload Identity
Federation — keyless auth — when you want production-grade credentials.)

---

## Keep it warm (kill cold starts)

Cloud Run scales to zero, so the first visit after idle takes ~10–30s. Point a
free uptime monitor (UptimeRobot / cron-job.org) at `https://<url>/api/health`
every few minutes and it stays warm. Or set `--min-instances 1` (small cost).

## Updating the data

Re-ingest locally (`python -m ingest` or via the app), then re-upload the DB to
the bucket (Path B) or rebuild/redeploy the image (Path A).
