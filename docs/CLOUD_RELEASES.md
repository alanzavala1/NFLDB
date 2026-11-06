# Versioned cloud release uploads

The offline worker first creates and validates a native bundle. Publication then
uploads that bundle and its matching capture ZIP into one new GCS prefix. The
upload operation never selects a current release or deploys the website.

```text
gs://BUCKET/native/releases/RELEASE_ID/
  reservation.json     exclusive upload reservation
  nfl.duckdb           validated database
  validation.json      native source/statistical/API validation report
  watermarks.json      acknowledged source versions
  release.json         native bundle hashes and validation policy
  captures.zip         matching portable core/passing inputs
  publication.json     completion manifest, uploaded last
```

`release.json` is the existing local bundle manifest. `publication.json`
connects that bundle to its captured inputs and records each uploaded file's
size, SHA256, MD5 and GCS generation. A generation identifies a particular cloud
object version; readers use it rather than silently accepting newer bytes at
the same name. The upload receipt also records the completion manifest's own
generation and SHA256.

## Upload

Use the existing authenticated Google Cloud CLI. From `api/`, with the locked
Python environment and an unused destination:

```powershell
uv run --locked python -m jobs.publish upload `
  --release data/releases/validated-release `
  --captures data/matching-captures.zip `
  --destination gs://BUCKET/native/releases/UNIQUE_RELEASE_ID
```

Linux accepts the same options with ordinary shell line continuations. The
worker's existing Workload Identity authentication can supply CLI credentials;
no additional Python cloud SDK or service-account key is introduced. On Windows,
the adapter invokes the installed SDK's bundled Python directly, keeping local
paths out of `cmd.exe` expansion.

The publisher:

1. Holds a read-only database lock, fingerprints the source bytes, and verifies
   the native bundle using the existing validation-policy and file-hash checks.
2. Streams every ZIP member, checks its SHA256 and validates the complete graph
   of manifests, declared files and child references. It recomputes the root
   collection identities and compares them and the seasons to the database's
   validation report. It then confirms that the source bytes stayed unchanged
   throughout those content checks. This needs no second extracted copy or R calculation.
3. Creates an exclusive reservation, then uploads each of the five payloads
   using `--if-generation-match=0`. Existing objects cause failure.
4. Supplies each expected MD5 for server-side transfer validation, then checks
   remote size/checksum metadata and records the returned generation.
5. Rechecks local inputs, the native bundle and the publisher code before
   uploading the completion manifest last.
6. Reads the pinned completion manifest back and verifies every recorded object
   generation and the native metadata links.

The native `validation_code_sha256` still identifies the analytics/API policy
that validated the database. A separate `publisher_code_sha256` records the
transport implementation. Transport changes can retain a compatible publication
format without changing the statistical validation record.

These are standard Cloud Storage operations. Google documents the
[create-only generation precondition](https://docs.cloud.google.com/storage/docs/request-preconditions)
and [server validation with `--content-md5`](https://docs.cloud.google.com/sdk/gcloud/reference/storage/cp).
SHA256 identifies payload bytes in the publication and is checked again when
files are downloaded; GCS's MD5 check protects the upload transfer.

## Verify an uploaded release

Record the JSON receipt emitted after upload. To check its exact manifest:

```powershell
uv run --locked python -m jobs.publish verify `
  --destination gs://BUCKET/native/releases/UNIQUE_RELEASE_ID `
  --manifest-generation GENERATION_FROM_RECEIPT `
  --manifest-sha256 SHA256_FROM_RECEIPT
```

Verification reads the recorded generations, compares remote transfer checksums
and sizes, checks SHA256 for the small downloaded metadata files, and checks the
native report, watermarks, bundle hashes, source identities and policy. It does
not download the large database/ZIP or rerun statistical validation. Deployment
must download the pinned objects, check their SHA256 values and run the existing
native bundle verifier before baking the database into an image.

Omitting the optional manifest identity discovers the prefix's current
completion marker, then pins its generation for the verification. Automated
deployment should consume the recorded identity from selection.

## Select a completed release

A selection is a small mutable JSON object pointing to one completed publication.
Its content pins the publication manifest's generation and SHA256. Keep selection
objects outside immutable release directories. Selection expresses the desired
release; it does not change an already running Cloud Run image.

For a known unused **trial** pointer:

```powershell
uv run --locked python -m jobs.publish select `
  --pointer gs://BUCKET/native/selection-trials/TRIAL_ID/current.json `
  --expected-generation 0 `
  --destination gs://BUCKET/native/releases/RELEASE_ID `
  --manifest-generation PUBLICATION_GENERATION `
  --manifest-sha256 PUBLICATION_SHA256
```

For subsequent updates, pass the pointer generation read **at the start of the
job's work**, rather than zero. The server accepts the update only while that
generation is still current. An older job cannot silently overwrite a selection
that another job changed in the meantime. The selector never refreshes its
expectation and retries a conflict automatically. Intentional rollback selects
an earlier compatible release using a fresh observed pointer generation.

Read a selection with:

```powershell
uv run --locked python -m jobs.publish current `
  --pointer gs://BUCKET/native/selection-trials/TRIAL_ID/current.json
```

The response includes `pointer_generation`, `pointer_sha256` and the selected
publication identity. Missing selections and authentication/read errors remain
errors; they are not treated as permission to initialize a new pointer.

## Download and verify the selected snapshot

```powershell
uv run --locked python -m jobs.publish download `
  --pointer gs://BUCKET/native/selection-trials/TRIAL_ID/current.json `
  --pointer-generation POINTER_GENERATION `
  --pointer-sha256 POINTER_SHA256 `
  --output data/new-selected-download
```

The identity options pin a recorded selection. Omitting them reads the latest
selection once and pins that version for the rest of the operation. Each payload
comes from the publication's exact recorded object generation. The SDK's standard
resumable/sliced file downloader writes into a private staging directory; bounded
copies then fill exclusively created output files, checked against SHA256, MD5
and size. A stalled SDK download is limited to 30 minutes per file. Budget for
temporary SDK files in addition to the completed output. The existing
native bundle verifier checks the downloaded database/report/watermark linkage
and the analytics validation policy.

```text
data/new-selected-download/
  release/             database and the three native metadata files
  download.json        verified local completion record, written last
  captures.zip         only with --include-captures
```

The serving/deployment consumer needs `release/`. Add `--include-captures` for a
refresh worker or archive replay; this also checks every downloaded capture
member and the source graph without extracting a second copy. The API image
does not need R or the input archive to serve the prepared database.

The command requires a new output directory and never replaces an existing
local snapshot. On ordinary failures it removes files it created and preserves
unexpected files from other actors. A killed process can leave an incomplete
directory; use a new output path for retries. Use an output only after the command
succeeds, and verify its native bundle again before packaging/deployment.

A selection update during a download does not mix releases: the download
finishes the snapshot it already pinned. The completion record retains that
selection and publication identity. Deployment must enforce its own rollout
ordering; the mutable selection is not a record of what is already serving.

## Failure handling

An incomplete prefix has no completion manifest and cannot be treated as a
published release. Failed uploads retain their reservation and any uploaded
objects for diagnosis; retries use a new release ID. The uploader never deletes
existing cloud objects or overwrites previous release files.

A client can lose its connection after the server has accepted the final
manifest. In that case, verify the existing destination before deciding whether
a new upload is needed. A valid completion manifest still represents a complete
upload even if the original caller did not receive its acknowledgment.

Immutability is enforced by the publisher's create-only protocol. Bucket
retention/IAM settings remain a separate concern. If an externally replaced
object's recorded generation is unavailable, verification fails; it does not
fall back to another version.

## Verified result: October 30, 2026

151 distinct targeted checks passed on Windows and Ubuntu 24.04. They cover
partial uploads, conflicting/concurrent publishers, changed local files and
publisher code, archive replacement during preflight, corrupt/mismatched capture
graphs, remote corruption and generation-pinned reads. Existing release,
candidate, source-provenance and refresh controls are included in that count.

A real probe using Google Cloud SDK 572.0.0 rejected an incorrect MD5 and a
second create-only write, and successfully read the pinned object version. A
subsequent real upload interrupted by an authentication-service DNS failure
left only a reservation and no completion manifest.

The completed upload contains the previously validated 1999–2026 database and
its matching 4,741-file capture archive, plus the three small native metadata
files. The ordinary upload command completed, and a separate ordinary verify
command matched its exact manifest generation/SHA256 and returned the same
receipt. The local bundle/archive and all five protected original databases
remained intact. The legacy cloud database/watermarks were unchanged during the
final upload. No native release was selected or deployed by this work.

The local end-to-end upload, including preflight and integrated verification,
took 17 minutes 14 seconds; the two large payloads total approximately 2.13 GB.
This reflects the local network connection, not a hosted-worker benchmark. The
large objects were checked with server-validated MD5 and pinned generation/size
metadata; download-time SHA256 verification remains part of the next consumer
integration. Publishing existing captures acknowledges no new upstream versions.

The receipt, standalone verification, independent cloud proof, test XML, SDK
version and diagnostic logs are kept under ignored `api/data/` with the
`publication-*-20261030` prefix. Keep the saved receipt for the next selection
step; it identifies the exact completed cloud release.

## Verified selection/download result: November 1, 2026

184 distinct targeted checks passed on Windows and Ubuntu 24.04. The new cases
cover stale/duplicate selection updates, intentional rollback, exact selection
reads, interrupted/corrupt downloads, preservation of existing snapshots and
unexpected files, code/local-file changes during downloads, missing pinned
objects, and SDK timeout cleanup.

A separate real GCS trial pointer was created and conditionally updated.
Duplicate initialization and a stale-generation update were rejected by the
server; the successful selection remained intact. The trial selected the
previously validated October 28 capture bundle, not freshly downloaded NFL data.

The ordinary download command then retrieved all five selected payloads,
including the capture ZIP, from their recorded object generations. SHA256, MD5
and sizes matched, the native bundle verified, and all 4,741 capture members and
their source graph passed. The completion record matched the recorded cloud
selection/publication identities. A fresh read-only API process successfully
handled 102 HTTP checks and rejected a persistent database write. A subsequent
audit confirmed the downloaded bytes, original publication inputs and all five
protected original databases were unchanged.

The first one-shot `gcloud storage cat` transfer stalled and eventually failed
with a read timeout; its partial output directory was removed without a completion
record. The adapter now uses the SDK's resumable file downloader and private
staging. The successful local run took 10 minutes 3 seconds, including remote
checks, both large files and archive verification. This is a local-network
measurement, not a GitHub-hosted worker benchmark.

Evidence remains ignored under `api/data/`: `selection-cloud-proof-20261101.json`,
`selection-cloud-receipt-20261101.json`, `selection-download-proof-20261101.json`,
`selection-api-proof-20261101.json`, related logs/test XML, and
`selected-cloud-download-retry-20261101/`. No production selection or deployment
was performed by this trial.

## Native preview deployment proof — November 1, 2026

The Docker build now keeps all local data outside its shared source context.
The native target receives only the four verified release files through a named
context; the transitional legacy target receives its own database through a
different named context. Both targets were built and inspected. The native image
contained no legacy database, captures, or experiments. The legacy image's
database retained its original SHA256.

The native image used code commit `9825057c20ec67ac11f4d601df046f55ef6fe9d4`
and the October 28 snapshot already published and downloaded above. It passed
102 API checks with real application startup, rejected a persistent database
write, and passed 24 reconciliation/assistant tests with a read-only container
filesystem. Local HTTP checks also verified the frontend and API.

The image was pushed to Artifact Registry and deployed by immutable digest:
`sha256:3d2b21a06dddad6cb76e94727453902097884bfd044bdcf2e2c9fd0c0e0a9bb4`.
The ordinary rollout script then completed three real Cloud Run operations on
the separate `nfldb-native-preview` service:

1. Created and verified revision `nfldb-native-preview-n-20261101-1`.
2. Created revision `nfldb-native-preview-n-20261101-2` at zero traffic, checked
   its tagged URL and image digest, rechecked the selection, and promoted it.
3. Verified the first revision through a tag and rolled traffic back to it.

After rollback, all 102 certified API paths also passed over actual network HTTP
against the [cloud preview](https://nfldb-native-preview-urbkyyex2a-uc.a.run.app),
along with health and frontend checks. Production remained on
`nfldb-00072-vs6` at 100% traffic; its recorded revision, URL and traffic metadata
were unchanged. No production selection or legacy bucket object was written.

Both preview revisions intentionally used the same verified image and captured
data. This proves real revision rollout/rollback plumbing, not a comparison
between different data releases. Candidate rejection, superseded selection, and
recovery after a failed promotion were additionally exercised against a stateful
Cloud Run stand-in. The related suite passed 65 tests on Linux; Windows passed
58 with the seven Linux shell tests skipped. Workflow syntax passed actionlint.
The GitHub workflow itself has not been pushed or dispatched; the real cloud
trial ran its ordinary script using the existing authenticated SDK.

The native validation policy remains `f72611443cf21bba4fc9ecec485459304b10e6094c4997339747b4ac16ef7ef4`.
No statistical definitions, tolerances or availability rules changed. Audits
confirmed all five protected databases, downloaded payloads, original release
and capture archive retained their hashes and no WALs appeared. Ignored evidence
is under `api/data/native-image-*20261101*`, `native-preview-*20261101*`,
`native-deployment-*20261101*`, and `legacy-image-*20261101*`.

## Production integration — November 6, 2026

The native workflows are active on `main`, and the legacy refresh/deploy workflows
are retired. Hosted preparation published
`native/releases/refresh-42251739850-1`, with publication generation
`1793986757725029` and SHA256
`e0b83c5282d851314a9d1e82e0c1469bf7adaea1d904d1da74678d7dcfadc550`.
Its database is 1,153,445,888 bytes and its matching capture ZIP is 1,144,284,148
bytes. Both candidate and release gates passed all 28 stored seasons and 102 API
paths. The analytics validation policy remains `f72611443cf21bba4fc9ecec485459304b10e6094c4997339747b4ac16ef7ef4`.

The production selection is
`gs://project-60bdbe3e-823a-46fb-b02-nfldb-data/native/production/current.json`.
At cutover it was generation `1793987317317652`, SHA256
`6d403dc4262ed6ed435ffcd99faba975139c0f6608e0e522f099b04283043671`.
Production deployment consumed that exact selection and passed its image and
public HTTP checks. The daily refresh is configured for this pointer and target.

See [DEPLOY.md](../DEPLOY.md#verified-production-cutover--november-6-2026) for the
workflow handoff fix, successful deployment runs, live revision and retained
rollback revision. The original combined run records a deployment failure after
successful publication; the completed data was reused for the successful manual
deployment. The next changed-source run will exercise the corrected combined
handoff. Ask model/streaming work and alternative frontend hosting remain later
milestones.
