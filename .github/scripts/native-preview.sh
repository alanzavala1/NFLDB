#!/usr/bin/env bash
# CI owns the per-service concurrency lock. This script never targets nfldb.
set -Eeuo pipefail
SERVICE=nfldb-native-preview
: "${PROJECT_ID:?}" "${REGION:?}" "${EVIDENCE:?}" "${OPERATION:?}"
mkdir -p "$EVIDENCE"
cloud() { gcloud --quiet --project "$PROJECT_ID" "$@"; }
describe() { cloud run services describe "$SERVICE" --region "$REGION" --format='json(status.url,status.traffic)'; }
current() { (cd api && .venv/bin/python -m jobs.deploy assert-current --download "$DOWNLOAD"); }

probe() {
  local url=$1
  curl -fsS --retry 3 --retry-all-errors --connect-timeout 10 --max-time 60 \
    "$url/api/health" | jq -e '.status == "ok"' >/dev/null
  curl -fsS --retry 3 --retry-all-errors --connect-timeout 10 --max-time 60 \
    "$url/api/seasons" | jq -e 'type == "array" and length > 0' >/dev/null
  curl -fsS --retry 3 --retry-all-errors --connect-timeout 10 --max-time 60 \
    "$url/" | grep -q 'id="root"'
}

# Query only public deployment metadata, never the service's environment secrets.
cloud run services list --region "$REGION" --filter="metadata.name=$SERVICE" \
  --format='json(metadata.name,status.url,status.traffic)' > "$EVIDENCE/before.json"
EXISTS=$(jq 'length' "$EVIDENCE/before.json")
[[ "$EXISTS" == 0 || "$EXISTS" == 1 ]]
PREVIOUS=$(jq -r '[.[0].status.traffic[]? | select(.percent == 100)][0].revisionName // empty' "$EVIDENCE/before.json")
if [[ "$EXISTS" == 1 && -z "$PREVIOUS" ]]; then
  echo 'Expected one revision serving 100%; inspect traffic before continuing.' >&2
  exit 1
fi
PROMOTED=0
recover() {
  local failure=$?
  trap - ERR
  if [[ "$PROMOTED" == 1 && -n "$PREVIOUS" ]]; then
    echo "Verification failed; restoring $PREVIOUS" >&2
    cloud run services update-traffic "$SERVICE" --region "$REGION" --to-revisions="$PREVIOUS=100" \
      || echo 'Automatic traffic restoration failed; use before.json for recovery.' >&2
  fi
  describe > "$EVIDENCE/after-failure.json" || true
  exit "$failure"
}
trap recover ERR

if [[ "$OPERATION" == deploy ]]; then
  : "${IMAGE:?}" "${DOWNLOAD:?}" "${GITHUB_RUN_ID:?}" "${GITHUB_RUN_ATTEMPT:?}"
  [[ "$IMAGE" =~ ^[a-z0-9.-]+-docker.pkg.dev/[a-z0-9-]+/nfldb/nfldb-native@sha256:[0-9a-f]{64}$ ]]
  current
  SUFFIX="n-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
  [[ "$SUFFIX" =~ ^n-[0-9]+-[0-9]+$ ]]
  REVISION="$SERVICE-$SUFFIX"
  FLAGS=()
  if [[ "$EXISTS" == 1 ]]; then
    # Remove any implicit LATEST traffic before creating another revision.
    cloud run services update-traffic "$SERVICE" --region "$REGION" --to-revisions="$PREVIOUS=100"
    FLAGS+=(--no-traffic)
  else
    # A new preview has no previous revision to preserve or roll back to.
    PROMOTED=1
  fi
  cloud run deploy "$SERVICE" --region "$REGION" --platform managed --image "$IMAGE" \
    --revision-suffix "$SUFFIX" --tag candidate --allow-unauthenticated \
    --memory 4Gi --cpu 2 --min-instances 0 --max-instances 1 --port 8080 "${FLAGS[@]}"
  TAG=candidate
else
  [[ "$OPERATION" == rollback && "$EXISTS" == 1 ]]
  REVISION=${ROLLBACK_REVISION:?Supply a previously verified preview revision}
  [[ "$REVISION" =~ ^nfldb-native-preview-[a-z0-9-]+$ ]]
  TAG=rollback-check
fi

cloud run revisions describe "$REVISION" --region "$REGION" \
  --format='json(metadata.name,metadata.labels,status.conditions,status.imageDigest)' > "$EVIDENCE/revision.json"
jq -e --arg service "$SERVICE" '
  .metadata.labels["serving.knative.dev/service"] == $service and
  any(.status.conditions[]; .type == "Ready" and .status == "True")
' "$EVIDENCE/revision.json" >/dev/null
if [[ "$OPERATION" == deploy ]]; then
  [[ $(jq -r '.status.imageDigest' "$EVIDENCE/revision.json") == "$IMAGE" ]]
else
  cloud run services update-traffic "$SERVICE" --region "$REGION" --set-tags="$TAG=$REVISION"
fi
describe > "$EVIDENCE/candidate.json"
URL=$(jq -er --arg tag "$TAG" '.status.traffic[] | select(.tag == $tag) | .url' "$EVIDENCE/candidate.json")
probe "$URL"
if [[ "$OPERATION" == deploy ]]; then current; fi
PROMOTED=1
cloud run services update-traffic "$SERVICE" --region "$REGION" --to-revisions="$REVISION=100"
describe > "$EVIDENCE/after.json"
jq -e --arg revision "$REVISION" \
  'any(.status.traffic[]; .revisionName == $revision and .percent == 100)' "$EVIDENCE/after.json" >/dev/null
probe "$(jq -er '.status.url' "$EVIDENCE/after.json")"
jq -n --arg operation "$OPERATION" --arg revision "$REVISION" --arg previous "$PREVIOUS" \
  --arg image "$(jq -r '.status.imageDigest' "$EVIDENCE/revision.json")" \
  '{operation:$operation, revision:$revision, previous_revision:$previous, image:$image, status:"verified"}' \
  > "$EVIDENCE/result.json"
cat "$EVIDENCE/result.json"
