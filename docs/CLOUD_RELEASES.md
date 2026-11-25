# Cloud releases

Publication stores a validated database and its matching captures in Cloud
Storage. Selection chooses the desired release. Deployment is a separate step.

Commands below run from `api/` with uv and an authenticated Google Cloud CLI.
Examples use Bash line continuations. Replace uppercase placeholders with values
from the operation's JSON receipt; use new local paths and unique release IDs.

## Upload and verify

```sh
uv run --locked python -m jobs.publish upload \
  --release data/validated-release --captures data/captures.zip \
  --destination gs://BUCKET/native/releases/RELEASE_ID

uv run --locked python -m jobs.publish verify \
  --destination gs://BUCKET/native/releases/RELEASE_ID \
  --manifest-generation PUBLICATION_GENERATION \
  --manifest-sha256 PUBLICATION_SHA256
```

The publisher verifies the local bundle and capture graph, reserves a new prefix
and uploads create-only objects. `publication.json` is written last:

```text
native/releases/RELEASE_ID/
  reservation.json
  nfl.duckdb
  validation.json
  watermarks.json
  release.json
  captures.zip
  publication.json
```

The completion manifest records sizes, checksums, source identities and exact
object generations. A generation identifies one cloud object version. Cloud
verification checks pinned metadata and native report links; it does not download
the full database/archive or rerun statistical calculations.

## Read or update a selection

```sh
uv run --locked python -m jobs.publish current \
  --pointer gs://BUCKET/native/candidates/current.json

uv run --locked python -m jobs.publish select \
  --pointer gs://BUCKET/native/candidates/current.json \
  --expected-generation POINTER_GENERATION \
  --destination gs://BUCKET/native/releases/RELEASE_ID \
  --manifest-generation PUBLICATION_GENERATION \
  --manifest-sha256 PUBLICATION_SHA256
```

A selection pins a completed publication. Use the pointer generation observed
before the job started preparing data. `--expected-generation 0` is only for a
new pointer. A concurrent change causes selection to fail rather than overwrite
a newer choice. Keep pointers outside immutable release directories.

The `current` receipt includes `pointer_generation`, `pointer_sha256` and the
publication identity. A selection does not identify what is already serving;
a running container keeps its baked database until deployment.

## Download a selected release

```sh
uv run --locked python -m jobs.publish download \
  --pointer gs://BUCKET/native/candidates/current.json \
  --pointer-generation POINTER_GENERATION --pointer-sha256 POINTER_SHA256 \
  --output data/selected-download
```

The command downloads the exact selected object generations, checks their bytes
and verifies the native bundle. Its output is:

```text
selected-download/
  release/       database, validation, watermarks and release manifest
  download.json  completion receipt
```

Add `--include-captures` when a worker needs `captures.zip`. Serving needs only
`release/`; it does not need R or the capture archive. Omitting pointer identity
options reads the current selection once and pins it for the download.

For local development, set `NFL_DB_PATH` to the downloaded
`release/nfl.duckdb`. For image builds, use `release/` as the data build context
in [deployment](../DEPLOY.md).

## Failure handling

- A prefix without `publication.json` is incomplete. Failed uploads retain their
  objects; retry with a new release ID.
- If the connection fails after the completion manifest was accepted, verify that
  destination before uploading another copy.
- Missing recorded object generations fail verification; readers do not substitute
  newer bytes. Bucket IAM and retention are separate from this create-only protocol.
- Downloads require a new directory. Ordinary failures clean up owned files;
  interrupted processes can leave partial output. Retry in a new directory.
- Temporary SDK download files need additional disk space. A pointer change during
  download does not mix releases; deployment separately checks rollout ordering.

See [local bundles](OFFLINE_RELEASES.md), [capture archives](CAPTURE_ARCHIVES.md)
and [refresh automation](NATIVE_REFRESH_AUTOMATION.md).
